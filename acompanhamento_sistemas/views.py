from __future__ import annotations

from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from auditoria.models import AuditLog

from .forms import (
    EntregaSistemaForm,
    EtapaSistemaAtualizacaoForm,
    InteressadoSistemaForm,
    NotaEtapaSistemaForm,
    SistemaFiltroForm,
    SistemaForm,
)
from .models import (
    EntregaSistema,
    EtapaSistema,
    HistoricoEtapaSistema,
    InteressadoSistema,
    InteressadoSistemaManual,
    Sistema,
)
from .services import adicionar_nota_etapa, atualizar_etapa_com_historico, criar_entrega_com_etapas


User = get_user_model()


def _registrar_auditoria_view(objeto, *, usuario, acao, changes=None):
    AuditLog.objects.create(
        user=usuario if getattr(usuario, "is_authenticated", False) else None,
        action=acao,
        content_type=ContentType.objects.get_for_model(objeto.__class__),
        object_id=str(objeto.pk),
        object_repr=str(objeto),
        changes=changes or {},
    )


def _enfileirar_erros_formulario(request, form):
    for _, erros in form.errors.items():
        for erro in erros:
            messages.error(request, erro)


def _timeline_sistema(sistema):
    itens = []
    for entrega in sistema.entregas.all():
        itens.append(
            SimpleNamespace(
                entrega=entrega,
                etapa=None,
                tipo_evento=HistoricoEtapaSistema.TipoEvento.CRIACAO,
                criado_em=entrega.criado_em,
                criado_por=entrega.criado_por,
                descricao=f"Ciclo {entrega.titulo} criado.",
                justificativa="",
                anexos=[],
                eh_criacao_entrega=True,
                timeline_titulo=f"Ciclo {entrega.titulo}: Criacao",
                get_tipo_evento_display=lambda: "Criacao",
            )
        )

    historicos = (
        HistoricoEtapaSistema.objects.filter(etapa__entrega__sistema=sistema)
        .exclude(tipo_evento=HistoricoEtapaSistema.TipoEvento.CRIACAO)
        .select_related("etapa", "etapa__entrega", "criado_por")
        .prefetch_related("anexos")
    )
    for historico in historicos:
        historico.eh_criacao_entrega = False
        historico.timeline_titulo = f"Ciclo {historico.etapa.entrega.titulo}: {historico.etapa.get_tipo_etapa_display()}"
        itens.append(historico)

    return sorted(itens, key=lambda item: (item.criado_em, getattr(item, "id", 0)), reverse=True)


class SistemaListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = ("acompanhamento_sistemas.view_sistema",)
    model = Sistema
    template_name = "acompanhamento_sistemas/list.html"
    context_object_name = "sistemas"

    def get_queryset(self):
        ultimo_historico = HistoricoEtapaSistema.objects.filter(
            etapa__entrega__sistema=OuterRef("pk")
        ).order_by("-criado_em", "-id")
        queryset = (
            Sistema.objects.select_related("criado_por", "atualizado_por")
            .prefetch_related(
                Prefetch(
                    "entregas__etapas",
                    queryset=EtapaSistema.objects.order_by("ordem", "id"),
                )
            )
            .annotate(
                ultimo_historico_em=Subquery(ultimo_historico.values("criado_em")[:1]),
                ultimo_historico_usuario_id=Subquery(ultimo_historico.values("criado_por_id")[:1]),
            )
            .distinct()
        )
        q = (self.request.GET.get("q") or "").strip()
        etapa = (self.request.GET.get("etapa") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        responsavel = (self.request.GET.get("responsavel") or "").strip()
        if q:
            queryset = queryset.filter(Q(nome__icontains=q) | Q(descricao__icontains=q))
        if etapa:
            queryset = queryset.filter(entregas__etapas__tipo_etapa=etapa)
        if status:
            queryset = queryset.filter(entregas__etapas__status=status)
        if responsavel and responsavel.isdigit():
            queryset = queryset.filter(ultimo_historico_usuario_id=int(responsavel))
        return queryset.order_by("nome").distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        responsaveis = User.objects.filter(
            pk__in=HistoricoEtapaSistema.objects.exclude(criado_por__isnull=True).values_list("criado_por_id", flat=True)
        ).order_by("first_name", "username")
        context["filtro_form"] = SistemaFiltroForm(self.request.GET or None, responsaveis=responsaveis)
        context["pode_editar_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.change_sistema")
        return context


class SistemaCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = ("acompanhamento_sistemas.add_sistema",)
    model = Sistema
    form_class = SistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        response = super().form_valid(form)
        _registrar_auditoria_view(self.object, usuario=self.request.user, acao=AuditLog.Action.CREATE, changes={"nome": self.object.nome})
        messages.success(self.request, "Sistema criado com sucesso. Agora você já pode lançar as entregas.")
        return response


class SistemaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = ("acompanhamento_sistemas.change_sistema",)
    model = Sistema
    form_class = SistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def form_valid(self, form):
        form.instance.atualizado_por = self.request.user
        _registrar_auditoria_view(
            self.object,
            usuario=self.request.user,
            acao=AuditLog.Action.UPDATE,
            changes={"nome": form.cleaned_data.get("nome"), "descricao": form.cleaned_data.get("descricao")},
        )
        messages.success(self.request, "Sistema atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pode_excluir_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.delete_sistema")
        return context


class SistemaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = ("acompanhamento_sistemas.delete_sistema",)
    model = Sistema
    template_name = "acompanhamento_sistemas/confirm_delete.html"

    def get_success_url(self):
        messages.success(self.request, "Sistema excluído com sucesso.")
        return reverse("acompanhamento_sistemas_list")


class SistemaDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = ("acompanhamento_sistemas.view_sistema",)
    model = Sistema
    template_name = "acompanhamento_sistemas/detail.html"
    context_object_name = "sistema"

    def get_queryset(self):
        return Sistema.objects.prefetch_related(
            "interessados__usuario",
            "interessados_manuais",
            Prefetch("entregas", queryset=EntregaSistema.objects.prefetch_related("etapas").order_by("ordem", "id")),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sistema = self.object
        context["entrega_form"] = kwargs.get("entrega_form") or EntregaSistemaForm()
        context["interessado_form"] = kwargs.get("interessado_form") or InteressadoSistemaForm(sistema=sistema)
        context["historicos"] = _timeline_sistema(sistema)
        context["abrir_modal_ciclo"] = kwargs.get("abrir_modal_ciclo", False)
        context["pode_editar_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.change_sistema")
        context["pode_criar_entrega"] = self.request.user.has_perm("acompanhamento_sistemas.add_entregasistema")
        context["pode_excluir_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.delete_sistema")
        return context


class EntregaSistemaCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("acompanhamento_sistemas.add_entregasistema",)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("acompanhamento_sistemas.add_entregasistema"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        sistema = get_object_or_404(Sistema, pk=pk)
        form = EntregaSistemaForm(request.POST)
        if form.is_valid():
            criar_entrega_com_etapas(
                sistema,
                usuario=request.user,
                titulo=form.cleaned_data["titulo"],
                descricao=form.cleaned_data["descricao"],
            )
            messages.success(request, "Novo ciclo criado com as 5 etapas obrigatórias.")
            return redirect("acompanhamento_sistemas_detail", pk=sistema.pk)
        messages.error(request, "Não foi possível criar o ciclo.")
        _enfileirar_erros_formulario(request, form)
        view = SistemaDetailView()
        view.setup(request, pk=pk)
        view.object = sistema
        return view.render_to_response(view.get_context_data(entrega_form=form, abrir_modal_ciclo=True))

    def handle_no_permission(self):
        raise Http404


class EntregaSistemaDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = ("acompanhamento_sistemas.view_entregasistema",)
    model = EntregaSistema
    template_name = "acompanhamento_sistemas/entrega_detail.html"
    context_object_name = "entrega"

    def get_queryset(self):
        return EntregaSistema.objects.select_related(
            "sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            Prefetch("etapas", queryset=EtapaSistema.objects.order_by("ordem", "id"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pode_editar_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.change_sistema")
        context["pode_excluir_ciclo"] = self.request.user.has_perm("acompanhamento_sistemas.delete_entregasistema")
        return context


class EntregaSistemaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = ("acompanhamento_sistemas.change_entregasistema",)
    model = EntregaSistema
    form_class = EntregaSistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def form_valid(self, form):
        form.instance.atualizado_por = self.request.user
        _registrar_auditoria_view(
            self.object,
            usuario=self.request.user,
            acao=AuditLog.Action.UPDATE,
            changes={"titulo": form.cleaned_data.get("titulo"), "descricao": form.cleaned_data.get("descricao")},
        )
        messages.success(self.request, "Ciclo atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modo_ciclo"] = True
        context["pode_excluir_ciclo"] = self.request.user.has_perm("acompanhamento_sistemas.delete_entregasistema")
        return context


class EntregaSistemaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = ("acompanhamento_sistemas.delete_entregasistema",)
    model = EntregaSistema
    template_name = "acompanhamento_sistemas/confirm_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modo_ciclo"] = True
        return context

    def get_success_url(self):
        sistema_pk = self.object.sistema.pk
        messages.success(self.request, "Ciclo excluído com sucesso.")
        return reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema_pk})


class EtapaSistemaDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = ("acompanhamento_sistemas.view_etapasistema",)
    model = EtapaSistema
    template_name = "acompanhamento_sistemas/etapa_detail.html"
    context_object_name = "etapa"

    def get_queryset(self):
        return EtapaSistema.objects.select_related(
            "entrega",
            "entrega__sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            "historicos__criado_por",
            "historicos__anexos",
            "entrega__sistema__interessados__usuario",
            "entrega__sistema__interessados_manuais",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        etapa = self.object
        sistema = etapa.entrega.sistema
        context["historicos"] = _timeline_sistema(sistema)
        context["etapa_form"] = kwargs.get("etapa_form") or EtapaSistemaAtualizacaoForm(instance=etapa)
        context["nota_form"] = kwargs.get("nota_form") or NotaEtapaSistemaForm()
        context["abrir_modal_nota"] = kwargs.get("abrir_modal_nota", False)
        context["interessado_form"] = kwargs.get("interessado_form") or InteressadoSistemaForm(sistema=sistema)
        context["pode_editar_etapa"] = self.request.user.has_perm("acompanhamento_sistemas.change_etapasistema")
        context["pode_editar_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.change_sistema")
        return context


class EtapaSistemaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("acompanhamento_sistemas.change_etapasistema",)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("acompanhamento_sistemas.change_etapasistema"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        etapa = get_object_or_404(EtapaSistema, pk=pk)
        form = EtapaSistemaAtualizacaoForm(request.POST, request.FILES, instance=etapa)
        if form.is_valid():
            etapa_atual = EtapaSistema.objects.get(pk=etapa.pk)
            atualizar_etapa_com_historico(
                etapa_atual,
                nova_data=form.cleaned_data["data_etapa"],
                novo_status=form.cleaned_data["status"],
                justificativa=form.cleaned_data.get("justificativa_status"),
                texto_nota=form.cleaned_data.get("texto_nota"),
                anexos=form.cleaned_data.get("anexos"),
                usuario=request.user,
                request=request,
            )
            messages.success(request, "Etapa atualizada com sucesso.")
            return redirect("acompanhamento_sistemas_etapa_detail", pk=etapa_atual.pk)
        messages.error(request, "Não foi possível atualizar a etapa.")
        _enfileirar_erros_formulario(request, form)
        view = EtapaSistemaDetailView()
        view.setup(request, pk=pk)
        view.object = etapa
        return view.render_to_response(view.get_context_data(etapa_form=form))

    def handle_no_permission(self):
        raise Http404


class EtapaSistemaNotaView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("acompanhamento_sistemas.change_etapasistema",)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("acompanhamento_sistemas.change_etapasistema"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        etapa = get_object_or_404(EtapaSistema, pk=pk)
        form = NotaEtapaSistemaForm(request.POST, request.FILES)
        if form.is_valid():
            adicionar_nota_etapa(
                etapa,
                texto=form.cleaned_data.get("texto_nota"),
                anexos=form.cleaned_data.get("anexos"),
                usuario=request.user,
                request=request,
            )
            messages.success(request, "Anotação registrada com sucesso.")
            return redirect("acompanhamento_sistemas_etapa_detail", pk=etapa.pk)
        messages.error(request, "Não foi possível registrar a anotação.")
        _enfileirar_erros_formulario(request, form)
        view = EtapaSistemaDetailView()
        view.setup(request, pk=pk)
        view.object = etapa
        return view.render_to_response(view.get_context_data(nota_form=form, abrir_modal_nota=True))

    def handle_no_permission(self):
        raise Http404


class InteressadoSistemaCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("acompanhamento_sistemas.change_sistema",)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("acompanhamento_sistemas.change_sistema"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        sistema = get_object_or_404(Sistema, pk=pk)
        form = InteressadoSistemaForm(request.POST, sistema=sistema)
        if form.is_valid():
            interessado = form.save(sistema, request.user)
            _registrar_auditoria_view(
                interessado,
                usuario=request.user,
                acao=AuditLog.Action.CREATE,
                changes={"tipo_interessado": interessado.tipo_interessado},
            )
            messages.success(request, "Interessado vinculado ao sistema.")
        else:
            messages.error(request, "Não foi possível adicionar o interessado.")
            _enfileirar_erros_formulario(request, form)
        proxima_url = request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk})
        return HttpResponseRedirect(proxima_url)

    def handle_no_permission(self):
        raise Http404


class InteressadoSistemaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("acompanhamento_sistemas.change_sistema",)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("acompanhamento_sistemas.change_sistema"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk, interessado_pk):
        sistema = get_object_or_404(Sistema, pk=pk)
        interessado = InteressadoSistema.objects.filter(pk=interessado_pk, sistema=sistema).first()
        if interessado is not None:
            _registrar_auditoria_view(interessado, usuario=request.user, acao=AuditLog.Action.DELETE, changes={"tipo_interessado": interessado.tipo_interessado})
            interessado.delete()
            messages.success(request, "Interessado removido.")
            return redirect(request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))
        interessado_manual = get_object_or_404(InteressadoSistemaManual, pk=interessado_pk, sistema=sistema)
        _registrar_auditoria_view(interessado_manual, usuario=request.user, acao=AuditLog.Action.DELETE, changes={"tipo_interessado": interessado_manual.tipo_interessado})
        interessado_manual.delete()
        messages.success(request, "Interessado removido.")
        return redirect(request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

    def handle_no_permission(self):
        raise Http404
