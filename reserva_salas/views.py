"""
Views do app `reserva_salas`.

Este módulo implementa o fluxo HTTP completo de salas e reservas usando Class
Based Views (CBVs) do Django. Ele integra:
- `models.py` para leitura/escrita dos dados transacionais;
- `forms.py` para validações de negócio no envio de formulários;
- templates em `templates/reserva_salas/` para renderização HTML;
- sistema de permissões/autenticação do Django para controle de acesso.

Também prepara dados derivados (incluindo dados de perfil/ramal do usuário) para
uso em telas de calendário, detalhe e confirmação de exclusão.
"""

from calendar import monthrange
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
import uuid
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ReservaForm, SalaForm
from .models import Reserva, Sala

User = get_user_model()


def _nome_curto(nome: str) -> str:
    """
    Reduz um nome completo para até duas palavras.

    Problema que resolve:
    - Mantém cartões de agenda compactos sem perder identificação mínima.

    Parâmetros:
    - `nome` (`str`): nome completo do usuário.

    Retorno:
    - `str`: versão curta do nome (máximo de dois termos).
    """
    partes = [parte for parte in (nome or "").split() if parte]
    return " ".join(partes[:2]) if partes else ""


def _dados_registro_usuario(usuario):
    """
    Normaliza dados de identificação do usuário responsável pela reserva.

    Problema que resolve:
    - Evita repetição de lógica de fallback para nome, ramal e e-mail em várias
      views/templates.

    Parâmetros:
    - `usuario`: instância de usuário (ou `None`).

    Retorno:
    - `dict`: dicionário com `nome`, `nome_curto`, `ramal` e `email`.

    Integração externa:
    - Lê dados complementares do perfil relacionado `ramal_perfil` quando
      disponível.
    """
    if not usuario:
        return {"nome": "", "nome_curto": "", "ramal": "", "email": ""}
    nome = usuario.get_full_name() or usuario.username or ""
    perfil = getattr(usuario, "ramal_perfil", None)
    return {
        "nome": nome,
        "nome_curto": _nome_curto(nome),
        "ramal": getattr(perfil, "ramal", "") or "",
        "email": getattr(perfil, "email_display", "") or "",
    }


class SalaListView(ListView):
    """
    Lista salas e embute agenda de reservas para visualização consolidada.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/` (rota base do app), retornando página de agenda com
      dados de salas e reservas serializados para o frontend.
    """

    model = Sala
    template_name = "reserva_salas/sala_list.html"
    context_object_name = "salas"

    def get_context_data(self, **kwargs):
        """
        Monta o contexto adicional `reservas_data` usado pelo calendário.

        Problema que resolve:
        - Entrega ao template uma estrutura pronta para renderização de eventos,
          incluindo metadados da sala e do usuário que registrou a reserva.

        Consulta ORM:
        - `Reserva.objects.select_related("sala", "registrado_por").all()`
        - Objetivo: carregar reservas com joins para evitar múltiplas consultas
          N+1 ao acessar sala e usuário em loop.

        Retorno:
        - `dict`: contexto padrão + lista de reservas normalizadas.
        """
        context = super().get_context_data(**kwargs)
        reservas = Reserva.objects.select_related("sala", "registrado_por").all()
        reservas_data = []
        for reserva in reservas:
            dados_usuario = _dados_registro_usuario(reserva.registrado_por)
            reservas_data.append(
                {
                    "id": reserva.pk,
                    "inicio": datetime.combine(reserva.data, reserva.hora_inicio).isoformat(),
                    "fim": datetime.combine(reserva.data, reserva.hora_fim).isoformat(),
                    "sala_id": reserva.sala_id,
                    "sala_nome": reserva.sala.nome,
                    "sala_localizacao": reserva.sala.localizacao,
                    "sala_cor": reserva.sala.cor,
                    "nome_evento": reserva.nome_evento,
                    "reservado_por_nome": dados_usuario["nome"],
                    "reservado_por_nome_curto": dados_usuario["nome_curto"],
                    "reservado_por_ramal": dados_usuario["ramal"],
                    "reservado_por_email": dados_usuario["email"],
                    "url": reverse("reservas_detail", kwargs={"pk": reserva.pk}),
                }
            )
        context["reservas_data"] = reservas_data
        return context


class ReservaListView(ListView):
    """
    Lista administrativa de reservas cadastradas.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/reservas/`, exibindo listagem tabular histórica.
    """

    model = Reserva
    template_name = "reserva_salas/reserva_list.html"
    context_object_name = "reservas"


class ReservaDashboardView(ListView):
    """
    Exibe dashboard de métricas de reservas de sala.

    Blocos entregues no MVP:
    - cards do mês atual (total, salas ativas e média de reuniões por dia);
    - gráfico de reuniões por mês;
    - gráfico de salas mais utilizadas por quantidade de eventos;
    - tabela de responsáveis com mais reservas.
    """

    model = Reserva
    template_name = "reserva_salas/reserva_dashboard.html"
    context_object_name = "reservas"

    def get_context_data(self, **kwargs):
        """
        Monta agregações para cards, gráficos e tabela do dashboard.
        """
        context = super().get_context_data(**kwargs)
        reservas_base = Reserva.objects.all()
        hoje = timezone.localdate()
        inicio_mes = hoje.replace(day=1)
        fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])

        reservas_mes = reservas_base.filter(data__range=(inicio_mes, fim_mes))
        total_reunioes_mes = reservas_mes.count()
        salas_ativas_mes = reservas_mes.values("sala_id").distinct().count()
        dias_com_reserva_mes = reservas_mes.values("data").distinct().count()
        media_reunioes_por_dia = (
            round(total_reunioes_mes / dias_com_reserva_mes, 2)
            if dias_com_reserva_mes
            else 0
        )

        reunioes_por_mes = (
            reservas_base.annotate(mes=TruncMonth("data"))
            .values("mes")
            .annotate(total=Count("id"))
            .order_by("mes")
        )
        grafico_reunioes_meses = {
            "labels": [item["mes"].strftime("%m/%Y") for item in reunioes_por_mes if item["mes"]],
            "values": [item["total"] for item in reunioes_por_mes if item["mes"]],
        }

        salas_mais_utilizadas = (
            reservas_base.values("sala__nome")
            .annotate(total=Count("id"))
            .order_by("-total", "sala__nome")
        )[:10]
        grafico_salas_top = {
            "labels": [item["sala__nome"] for item in salas_mais_utilizadas],
            "values": [item["total"] for item in salas_mais_utilizadas],
        }

        ranking_raw = list(
            reservas_base.filter(registrado_por__isnull=False)
            .values("registrado_por_id")
            .annotate(total=Count("id"))
            .order_by("-total", "registrado_por_id")[:15]
        )
        user_ids = [row["registrado_por_id"] for row in ranking_raw]
        usuarios = User.objects.filter(id__in=user_ids).select_related("ramal_perfil")
        usuarios_por_id = {usuario.id: usuario for usuario in usuarios}
        ranking_pessoas = []
        for row in ranking_raw:
            usuario = usuarios_por_id.get(row["registrado_por_id"])
            if not usuario:
                continue
            dados = _dados_registro_usuario(usuario)
            ranking_pessoas.append(
                {
                    "nome": dados["nome"] or usuario.username,
                    "ramal": dados["ramal"] or "-",
                    "email": dados["email"] or "-",
                    "total": row["total"],
                }
            )

        context.update(
            {
                "total_reunioes_mes": total_reunioes_mes,
                "salas_ativas_mes": salas_ativas_mes,
                "media_reunioes_por_dia": media_reunioes_por_dia,
                "mes_referencia": hoje.strftime("%m/%Y"),
                "grafico_reunioes_meses": grafico_reunioes_meses,
                "grafico_salas_top": grafico_salas_top,
                "ranking_pessoas": ranking_pessoas,
            }
        )
        return context


def reservas_dashboard_exportar(request):
    """
    Exporta reservas filtradas do dashboard em arquivo XLSX.

    Filtros aceitos:
    - `mes_ref`: no formato `MM/YYYY` (ex.: 03/2026)
    - `sala_nome`: nome exato da sala exibido no gráfico de ranking
    """

    try:
        from openpyxl import Workbook
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dependência ausente: instale openpyxl para exportação XLSX."
        ) from exc

    queryset = (
        Reserva.objects.select_related("sala", "registrado_por", "registrado_por__ramal_perfil")
        .order_by("-data", "-hora_inicio")
    )
    partes_nome = ["reservas-dashboard"]

    mes_ref = (request.GET.get("mes_ref") or "").strip()
    if mes_ref:
        try:
            data_referencia = datetime.strptime(mes_ref, "%m/%Y").date()
        except ValueError:
            return HttpResponse(
                "Parâmetro mes_ref inválido. Use MM/YYYY.",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
        inicio_mes = data_referencia.replace(day=1)
        fim_mes = data_referencia.replace(day=monthrange(data_referencia.year, data_referencia.month)[1])
        queryset = queryset.filter(data__range=(inicio_mes, fim_mes))
        partes_nome.append(data_referencia.strftime("%Y-%m"))

    sala_nome = (request.GET.get("sala_nome") or "").strip()
    if sala_nome:
        queryset = queryset.filter(sala__nome=sala_nome)
        sala_slug = "".join(ch if ch.isalnum() else "-" for ch in sala_nome.lower()).strip("-")
        partes_nome.append(sala_slug[:40] or "sala")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reservas"
    sheet.append(
        [
            "ID",
            "Data",
            "Hora Início",
            "Hora Fim",
            "Sala",
            "Evento",
            "Responsável Evento",
            "Quantidade Pessoas",
            "Reservado Por",
            "Ramal",
            "E-mail",
        ]
    )

    for reserva in queryset:
        dados_usuario = _dados_registro_usuario(reserva.registrado_por)
        sheet.append(
            [
                reserva.pk,
                reserva.data.strftime("%d/%m/%Y"),
                reserva.hora_inicio.strftime("%H:%M"),
                reserva.hora_fim.strftime("%H:%M"),
                reserva.sala.nome,
                reserva.nome_evento,
                reserva.responsavel_evento,
                reserva.quantidade_pessoas,
                dados_usuario["nome"] or "",
                dados_usuario["ramal"] or "",
                dados_usuario["email"] or "",
            ]
        )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = "-".join(partes_nome) + ".xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class SalaDetailView(DetailView):
    """
    Exibe detalhes de uma sala específica com timeline de reservas futuras.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/<pk>/`.
    """

    model = Sala
    template_name = "reserva_salas/sala_detail.html"
    context_object_name = "sala"

    def get_context_data(self, **kwargs):
        """
        Adiciona reservas futuras paginadas no contexto da sala.

        Regras de negócio:
        - Somente eventos cujo fim é maior/igual ao momento atual entram na
          timeline futura.

        Consulta ORM:
        - Filtra reservas da sala atual e ordena por data/hora para construir a
          linha do tempo cronológica.

        Retorno:
        - `dict`: contexto do detalhe com dados de paginação da timeline.
        """
        context = super().get_context_data(**kwargs)
        # Usa timezone do Django (America/Sao_Paulo) em vez do horario do SO.
        now = timezone.localtime().replace(tzinfo=None)
        reservas = (
            Reserva.objects.filter(sala=self.object)
            .order_by("data", "hora_inicio")
        )
        # Filtra em memória usando propriedades datetime para comparação exata
        # de intervalo, preservando clareza da regra temporal.
        futuras = [reserva for reserva in reservas if reserva.fim_datetime >= now]
        from django.core.paginator import Paginator
        page_number = self.request.GET.get("timeline_page", "1")
        paginator = Paginator(futuras, 6)
        page_obj = paginator.get_page(page_number)
        context["reservas_futuras"] = page_obj.object_list
        context["reservas_futuras_page"] = page_obj
        context["reservas_futuras_paginator"] = paginator
        # Preserva query params já existentes ao trocar de página na timeline,
        # removendo apenas o parâmetro de paginação da própria timeline.
        params_sem_pagina = self.request.GET.copy()
        params_sem_pagina.pop("timeline_page", None)
        base_query = params_sem_pagina.urlencode()
        context["timeline_page_base"] = (
            f"?{base_query}&timeline_page=" if base_query else "?timeline_page="
        )
        return context


class SalaCreateView(PermissionRequiredMixin, CreateView):
    """
    Controla criação de novas salas com verificação de permissão específica.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/nova/`: exibe formulário.
    - `POST /reserva-salas/nova/`: cria registro quando válido.

    Regra de acesso:
    - Exige permissão `reserva_salas.add_sala`.
    """

    model = Sala
    form_class = SalaForm
    template_name = "reserva_salas/sala_form.html"
    success_url = reverse_lazy("salas_list")
    permission_required = "reserva_salas.add_sala"


class SalaUpdateView(PermissionRequiredMixin, UpdateView):
    """
    Controla edição de dados da sala.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/<pk>/editar/`.
    - `POST /reserva-salas/<pk>/editar/`.

    Regra de acesso:
    - Exige permissão `reserva_salas.change_sala`.
    """

    model = Sala
    form_class = SalaForm
    template_name = "reserva_salas/sala_form.html"
    permission_required = "reserva_salas.change_sala"

    def get_success_url(self):
        """
        Retorna para o detalhe da sala após atualização bem-sucedida.
        """
        return self.object.get_absolute_url()


class SalaDeleteView(PermissionRequiredMixin, DeleteView):
    """
    Controla exclusão de salas, exibindo previamente eventos relacionados.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/<pk>/excluir/`: confirmação com impactos.
    - `POST /reserva-salas/<pk>/excluir/`: remove a sala.

    Regra de acesso:
    - Exige permissão `reserva_salas.delete_sala`.
    """

    model = Sala
    template_name = "reserva_salas/sala_confirm_delete.html"
    success_url = reverse_lazy("salas_list")
    permission_required = "reserva_salas.delete_sala"

    def get_context_data(self, **kwargs):
        """
        Monta a lista de reservas impactadas para transparência antes da exclusão.

        Consulta ORM:
        - Busca eventos da sala com `select_related` do usuário/perfil para evitar
          N+1 ao montar nome e ramal em loop.

        Retorno:
        - `dict`: contexto com `eventos_relacionados` para a tela de confirmação.
        """
        context = super().get_context_data(**kwargs)
        eventos = (
            Reserva.objects.filter(sala=self.object)
            .select_related("registrado_por", "registrado_por__ramal_perfil")
            .order_by("data", "hora_inicio")
        )
        eventos_data = []
        for evento in eventos:
            usuario = "-"
            ramal = "-"
            if evento.registrado_por:
                usuario = (
                    evento.registrado_por.get_full_name()
                    or evento.registrado_por.username
                )
                perfil = getattr(evento.registrado_por, "ramal_perfil", None)
                if perfil and perfil.ramal:
                    ramal = perfil.ramal
            eventos_data.append(
                {
                    "dia": evento.data,
                    "hora_inicio": evento.hora_inicio,
                    "hora_fim": evento.hora_fim,
                    "evento": evento.nome_evento,
                    "usuario": usuario,
                    "ramal": ramal,
                }
            )
        context["eventos_relacionados"] = eventos_data
        return context


class ReservaDetailView(DetailView):
    """
    Exibe detalhes de uma reserva específica.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/reservas/<pk>/`.
    """

    model = Reserva
    template_name = "reserva_salas/reserva_detail.html"
    context_object_name = "reserva"

    def get_context_data(self, **kwargs):
        """
        Envia ao template dados derivados do usuário que registrou a reserva.

        Retorno:
        - `dict`: contexto da reserva com variações de identificação do autor.
        """
        context = super().get_context_data(**kwargs)
        dados_usuario = _dados_registro_usuario(self.object.registrado_por)
        context["reservado_por_nome_curto"] = dados_usuario["nome_curto"]
        context["reservado_por_ramal"] = dados_usuario["ramal"]
        context["reservado_por_email"] = dados_usuario["email"]
        perfil = getattr(self.object.registrado_por, "ramal_perfil", None)
        if perfil and getattr(perfil, "pk", None):
            context["reservado_por_url"] = reverse("ramais_detail", kwargs={"pk": perfil.pk})
        elif dados_usuario["nome"]:
            query = urlencode({"q": dados_usuario["nome"]})
            context["reservado_por_url"] = f"{reverse('ramais_list')}?{query}"
        else:
            context["reservado_por_url"] = ""
        return context


class ReservaCreateView(UserPassesTestMixin, CreateView):
    """
    Controla criação de reservas individuais e em série recorrente.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/reservas/nova/`.
    - `POST /reserva-salas/reservas/nova/`.

    Regra de acesso:
    - Apenas usuários autenticados podem criar reservas.
    """

    model = Reserva
    form_class = ReservaForm
    template_name = "reserva_salas/reserva_form.html"
    success_url = reverse_lazy("reservas_list")

    def test_func(self):
        """
        Valida permissão mínima para criar reserva.

        Retorno:
        - `bool`: `True` para usuário autenticado.
        """
        return self.request.user.is_authenticated

    def form_valid(self, form):
        """
        Persiste reserva única ou múltiplas ocorrências de uma série recorrente.

        Regras de negócio:
        - Sem recorrência (ou série de 1 ocorrência), usa fluxo padrão do ModelForm.
        - Com recorrência, cria uma reserva por data calculada e associa todas ao
          mesmo `serie_id`, permitindo edição/exclusão em lote no futuro.

        Consulta ORM:
        - Usa `Reserva.objects.create(...)` para cada ocorrência da série.

        Retorno:
        - `HttpResponseRedirect`: para lista de reservas após sucesso.
        """
        recurrence_dates = form.get_recurrence_dates()
        if not recurrence_dates or len(recurrence_dates) <= 1:
            return super().form_valid(form)

        data = form.cleaned_data
        registrado_por = self.request.user if self.request.user.is_authenticated else None
        serie_id = uuid.uuid4()
        for occ_date in recurrence_dates:
            Reserva.objects.create(
                sala=data["sala"],
                data=occ_date,
                hora_inicio=data["hora_inicio"],
                hora_fim=data["hora_fim"],
                nome_evento=data["nome_evento"],
                responsavel_evento=data["responsavel_evento"],
                quantidade_pessoas=data["quantidade_pessoas"],
                televisao=data["televisao"],
                projetor=data["projetor"],
                som=data["som"],
                microfone_evento=data["microfone_evento"],
                som_evento=data["som_evento"],
                mesa_som_evento=data["mesa_som_evento"],
                videowall=data["videowall"],
                wifi=data["wifi"],
                registrado_por=registrado_por,
                serie_id=serie_id,
            )
        return redirect(self.success_url)

    def get_initial(self):
        """
        Pré-preenche data da reserva quando recebida por query string.

        Problema que resolve:
        - Facilita criação de reservas a partir de cliques em datas da agenda.

        Entrada:
        - Query param opcional `data` no formato ISO (`YYYY-MM-DD`).

        Retorno:
        - `dict`: dados iniciais do formulário.
        """
        initial = super().get_initial()
        data_param = self.request.GET.get("data")
        if data_param:
            try:
                from datetime import date

                initial["data"] = date.fromisoformat(data_param)
            except ValueError:
                # Ignora valor inválido sem interromper a experiência do usuário.
                pass
        return initial


class ReservaUpdateView(UserPassesTestMixin, UpdateView):
    """
    Controla edição de reservas individuais e atualização em lote de séries.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/reservas/<pk>/editar/`.
    - `POST /reserva-salas/reservas/<pk>/editar/`.
    """

    model = Reserva
    form_class = ReservaForm
    template_name = "reserva_salas/reserva_form.html"

    def test_func(self):
        """
        Define autorização de edição da reserva.

        Regra de negócio:
        - Staff ou usuário com `change_reserva` pode editar qualquer reserva.
        - Usuário comum edita apenas reservas que ele próprio registrou.

        Retorno:
        - `bool`: se a edição é permitida.
        """
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.has_perm("reserva_salas.change_reserva"):
            return True
        return self.get_object().registrado_por_id == user.id

    def get_success_url(self):
        """
        Retorna para a página de detalhe da própria reserva após salvar.
        """
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        """
        Inclui no contexto o tamanho da série recorrente, quando aplicável.

        Consulta ORM:
        - Conta quantas reservas compartilham o mesmo `serie_id`.

        Retorno:
        - `dict`: contexto padrão acrescido de `serie_count`.
        """
        context = super().get_context_data(**kwargs)
        reserva = context.get("reserva")
        if reserva is None:
            reserva = self.object
        if reserva and reserva.serie_id:
            context["serie_count"] = (
                Reserva.objects.filter(serie_id=reserva.serie_id).count()
            )
        return context

    def form_valid(self, form):
        """
        Aplica alteração em uma ocorrência ou em toda a série recorrente.

        Regras de negócio:
        - `apply_scope=single`: edição padrão apenas da ocorrência atual.
        - `apply_scope=all`: atualiza em lote todos os registros com mesmo
          `serie_id`, mantendo as datas originais de cada ocorrência.

        Consulta ORM:
        - `Reserva.objects.filter(serie_id=...).update(...)` para operação em lote.

        Retorno:
        - `HttpResponseRedirect` para detalhe da reserva.
        """
        apply_scope = self.request.POST.get("apply_scope", "single")
        if form.is_recurring_series() and apply_scope == "all":
            data = form.cleaned_data
            Reserva.objects.filter(serie_id=self.object.serie_id).update(
                sala=data["sala"],
                hora_inicio=data["hora_inicio"],
                hora_fim=data["hora_fim"],
                nome_evento=data["nome_evento"],
                responsavel_evento=data["responsavel_evento"],
                quantidade_pessoas=data["quantidade_pessoas"],
                televisao=data["televisao"],
                projetor=data["projetor"],
                som=data["som"],
                microfone_evento=data["microfone_evento"],
                som_evento=data["som_evento"],
                mesa_som_evento=data["mesa_som_evento"],
                videowall=data["videowall"],
                wifi=data["wifi"],
            )
            return redirect(self.get_success_url())
        return super().form_valid(form)


class ReservaDeleteView(UserPassesTestMixin, DeleteView):
    """
    Controla exclusão de reservas individuais ou de toda série recorrente.

    Fluxo HTTP controlado:
    - `GET /reserva-salas/reservas/<pk>/excluir/`.
    - `POST /reserva-salas/reservas/<pk>/excluir/`.
    """

    model = Reserva
    template_name = "reserva_salas/reserva_confirm_delete.html"
    success_url = reverse_lazy("reservas_list")

    def test_func(self):
        """
        Define autorização de exclusão da reserva.

        Regra de negócio:
        - Mesmo critério usado na edição: staff/permissão específica ou autor.

        Retorno:
        - `bool`: se a exclusão é permitida.
        """
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.has_perm("reserva_salas.delete_reserva"):
            return True
        return self.get_object().registrado_por_id == user.id

    def get_context_data(self, **kwargs):
        """
        Disponibiliza quantidade de ocorrências da série para UX de confirmação.

        Consulta ORM:
        - Conta registros por `serie_id` para informar impacto da ação em lote.

        Retorno:
        - `dict`: contexto com `serie_count` quando aplicável.
        """
        context = super().get_context_data(**kwargs)
        reserva = context.get("object")
        if reserva and reserva.serie_id:
            context["serie_count"] = (
                Reserva.objects.filter(serie_id=reserva.serie_id).count()
            )
        return context

    def post(self, request, *args, **kwargs):
        """
        Executa exclusão de uma ocorrência ou de toda a série recorrente.

        Regra de negócio:
        - Quando `apply_scope=all` e existe `serie_id`, remove todas as reservas
          da série em uma única operação.

        Consulta ORM:
        - `Reserva.objects.filter(serie_id=...).delete()` para remoção em lote.

        Retorno:
        - `HttpResponseRedirect` para listagem de reservas.
        """
        self.object = self.get_object()
        apply_scope = request.POST.get("apply_scope", "single")
        if self.object.serie_id and apply_scope == "all":
            Reserva.objects.filter(serie_id=self.object.serie_id).delete()
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)
