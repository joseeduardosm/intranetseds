"""
Views HTTP do app `lousa_digital`.

Este módulo implementa o fluxo completo da lousa:
- filtro de visibilidade de processos por usuário/grupo;
- monitoramento de prazo de encaminhamentos;
- timeline de eventos (auditoria e notas);
- operações de criação, edição, exclusão e devolução.

Integra-se com:
- `models.py` para leitura/escrita de domínio;
- `forms.py` para validação de payload;
- templates `templates/lousa_digital/*` para renderização de interface.
"""

import math
from collections import Counter
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, F, Func, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView
from django.utils import timezone

from .forms import EncaminhamentoForm, NotaTimelineForm, ProcessoForm
from .models import Encaminhamento, EventoTimeline, Processo


User = get_user_model()
LOUSA_ABAS = Processo.abas_origem()


def _registrar_evento(processo, tipo, descricao, usuario=None, encaminhamento=None):
    """Cria evento de timeline vinculado ao processo.

    Parâmetros:
    - `processo`: instância de `Processo` alvo do evento.
    - `tipo`: valor do enum `EventoTimeline.Tipo`.
    - `descricao`: texto de auditoria/nota exibido ao usuário.
    - `usuario`: autor opcional do evento.
    - `encaminhamento`: vínculo opcional com encaminhamento específico.
    """

    EventoTimeline.objects.create(
        processo=processo,
        tipo=tipo,
        descricao=descricao,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        encaminhamento=encaminhamento,
    )


def _formatar_duracao(minutos: int) -> str:
    """Formata minutos em string legível (`xh ymin`, `xh` ou `zmin`)."""

    horas = minutos // 60
    mins = minutos % 60
    if horas and mins:
        return f"{horas}h {mins}min"
    if horas:
        return f"{horas}h"
    return f"{mins}min"


def _formatar_dias(minutos: int) -> str:
    """Converte minutos para dias corridos arredondando para cima."""

    dias = math.ceil(max(minutos, 0) / (60 * 24))
    return f"{dias} dias"


def _formatar_dias_inteiros(dias: int) -> str:
    """Formata quantidade de dias inteiros para exibição."""

    dias = max(int(dias), 0)
    return f"{dias} dia" if dias == 1 else f"{dias} dias"


def _formatar_percentual_ptbr(valor: float) -> str:
    """Formata percentual com separador decimal em padrão pt-BR."""

    return f"{valor:.2f}".replace(".", ",")


def _nome_duas_primeiras_partes(nome: str) -> str:
    """Retorna apenas as duas primeiras palavras do nome informado."""

    partes = [parte for parte in (nome or "").strip().split() if parte]
    if not partes:
        return ""
    return " ".join(partes[:2])


def _nome_usuario_dashboard(usuario) -> str:
    """Normaliza nome de usuário para exibição em rankings do dashboard."""

    if not usuario:
        return "Sistema"
    return usuario.get_full_name() or usuario.username or "Sistema"


def _aba_lousa_ativa(valor, default=None) -> str:
    """Resolve a aba válida da lousa a partir do valor informado."""

    aba_padrao = default or LOUSA_ABAS[0]
    return Processo.normalizar_aba_origem(valor, default=aba_padrao)


def _contagem_processos_por_aba(usuario, arquivo_morto=False) -> dict:
    """Agrupa a quantidade de processos por aba/origem."""

    contagens = {aba: 0 for aba in LOUSA_ABAS}
    processos = (
        _processos_visiveis_para_usuario(usuario)
        .filter(arquivo_morto=arquivo_morto, caixa_origem__in=LOUSA_ABAS)
        .order_by()
        .values("caixa_origem")
        .annotate(total=Count("id", distinct=True))
    )
    for item in processos:
        aba = _aba_lousa_ativa(item["caixa_origem"], default="")
        if aba:
            contagens[aba] = item["total"]
    return contagens


def _serie_diaria_ultimos_30_dias(queryset, campo_data: str) -> dict:
    """Gera série diária fixa dos últimos 30 dias (incluindo hoje)."""

    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=29)
    agregados = Counter()

    for valor in queryset.values_list(campo_data, flat=True):
        if not valor:
            continue
        if hasattr(valor, "hour"):
            valor = timezone.localtime(valor).date()
        if valor < inicio or valor > hoje:
            continue
        agregados[valor] += 1

    labels = []
    values = []
    cursor = inicio
    while cursor <= hoje:
        labels.append(cursor.strftime("%d/%m"))
        values.append(agregados.get(cursor, 0))
        cursor += timedelta(days=1)
    return {"labels": labels, "values": values}


def _faixa_prazo_dashboard(prazo_data) -> tuple[str, str]:
    """Classifica o prazo em faixas operacionais do dashboard."""

    hoje = timezone.localdate()
    delta = (prazo_data - hoje).days
    if delta < 0:
        return ("vencidos", "Vencidos")
    if delta == 0:
        return ("vence_hoje", "Vence hoje")
    if delta <= 3:
        return ("ate_3", "1-3 dias")
    if delta <= 7:
        return ("ate_7", "4-7 dias")
    return ("acima_7", "Acima de 7 dias")


def _dados_prazo(encaminhamento: Encaminhamento):
    """Consolida métricas de SLA de um encaminhamento.

    Retorno:
    - dicionário com duração total, consumida, restante, atraso e valores formatados.
    """

    agora = timezone.now()
    inicio_data = timezone.localtime(encaminhamento.data_inicio).date()
    total_dias = max((encaminhamento.prazo_data - inicio_data).days, 1)
    if encaminhamento.data_conclusao is None:
        # Regra da lousa: contagem por dias, sem considerar o dia do encaminhamento.
        hoje_local = timezone.localdate()
        decorridos_dias = max((hoje_local - inicio_data).days, 0)
        consumido = min((decorridos_dias / total_dias) * 100, 100)
        restante_dias = max(total_dias - decorridos_dias, 0)
        limite = encaminhamento.prazo_limite
        atrasado = agora > limite
        inicio_iso = encaminhamento.data_inicio.isoformat()
    else:
        fim = encaminhamento.data_conclusao
        fim_data = timezone.localtime(fim).date()
        decorridos_dias = max((fim_data - inicio_data).days, 0)
        consumido = min((decorridos_dias / total_dias) * 100, 100)
        restante_dias = max(total_dias - decorridos_dias, 0)
        atrasado = fim > encaminhamento.prazo_limite
        inicio_iso = encaminhamento.data_inicio.isoformat()
    return {
        "decorridos": decorridos_dias,
        "total": total_dias,
        "total_dias": total_dias,
        "consumido": consumido,
        "restante": restante_dias,
        "atrasado": atrasado,
        "decorridos_fmt": _formatar_dias_inteiros(decorridos_dias),
        "total_fmt": _formatar_dias_inteiros(total_dias),
        "restante_fmt": _formatar_dias_inteiros(restante_dias),
        "restante_dias_fmt": _formatar_dias_inteiros(restante_dias),
        "inicio_iso": inicio_iso,
        "consumido_fmt": _formatar_percentual_ptbr(consumido),
    }


def _dados_alerta_prazo(dados_prazo: dict) -> dict:
    """Define exibição do alerta textual ancorado ao avanço da barra."""

    restante = int(dados_prazo.get("restante", 0) or 0)
    consumido = float(dados_prazo.get("consumido", 0) or 0)
    atrasado = bool(dados_prazo.get("atrasado"))
    exibir = True
    if atrasado:
        texto = "Prazo vencido"
        classe = "is-danger"
    elif restante == 0:
        texto = "Vence hoje"
        classe = "is-danger"
    else:
        texto = f"Faltam {_formatar_dias_inteiros(restante)}"
        classe = "is-warning" if restante <= 3 else "is-safe"
    posicao = min(max(consumido, 0), 100)
    return {
        "exibir": exibir,
        "texto": texto,
        "classe": classe,
        "posicao": _formatar_percentual_ptbr(posicao),
    }


def _processos_visiveis_para_usuario(usuario):
    """Define escopo de visibilidade de processos para o usuário logado.

    Regras:
    - superusuário vê todos;
    - usuário comum vê processos próprios;
    - usuário comum também vê processos cujo criador esteja em grupos que ele possui.
    """

    _arquivar_processos_sem_encaminhamento()
    queryset = Processo.objects.all()
    if not getattr(usuario, "is_authenticated", False):
        return queryset.none()
    if getattr(usuario, "is_superuser", False):
        return queryset
    grupos_ids = list(usuario.groups.values_list("id", flat=True))
    filtro = Q(criado_por=usuario)
    if grupos_ids:
        # Regra principal: visibilidade por grupos atuais do criador do processo.
        filtro |= Q(criado_por__groups__id__in=grupos_ids)
    return queryset.filter(filtro).distinct()


def _arquivar_processos_sem_encaminhamento():
    """Marca automaticamente como arquivo morto processos sem encaminhamento por 20 dias.

    Regras:
    - processo ainda não está em arquivo morto;
    - não possui nenhum encaminhamento;
    - foi criado há pelo menos 20 dias.

    Também registra um único evento de timeline para auditoria.
    """

    limite = timezone.now() - timedelta(days=20)
    processos = list(
        Processo.objects.filter(
            arquivo_morto=False,
            criado_em__lte=limite,
            encaminhamentos__isnull=True,
        ).distinct()
    )
    if not processos:
        return 0

    for processo in processos:
        processo.arquivo_morto = True
        processo.save(update_fields=["arquivo_morto", "atualizado_em"])
        if not EventoTimeline.objects.filter(
            processo=processo,
            descricao="Enviado automaticamente para arquivo morto após 20 dias sem encaminhamento.",
        ).exists():
            _registrar_evento(
                processo,
                EventoTimeline.Tipo.PROCESSO_EDITADO,
                "Enviado automaticamente para arquivo morto após 20 dias sem encaminhamento.",
            )
    return len(processos)


class ProcessoListView(LoginRequiredMixin, ListView):
    """Controla a tela principal da lousa com filtros, paginação e cards/tabela."""

    model = Processo
    template_name = "lousa_digital/processo_list.html"
    context_object_name = "processos"
    paginate_by = 24

    def _get_aba_ativa(self):
        """Retorna a aba atualmente selecionada na lousa."""

        return _aba_lousa_ativa(self.request.GET.get("aba"))

    def get_queryset(self):
        """Monta queryset otimizado com indicadores de prazo e filtros de busca.

        ORM relevante:
        - `Exists` e `Subquery` para detectar ativo e ordenar por prazo mais próximo;
        - `Prefetch` para carregar encaminhamentos sem N+1;
        - filtros dinâmicos por texto e status.
        """

        encaminhamentos_ativos = Encaminhamento.objects.filter(
            processo_id=OuterRef("pk"),
            data_conclusao__isnull=True,
        ).order_by("prazo_data", "data_inicio")
        queryset = (
            _processos_visiveis_para_usuario(self.request.user)
            .filter(caixa_origem=self._get_aba_ativa())
            .annotate(
                possui_ativo=Exists(encaminhamentos_ativos),
                prazo_ativo_ordenacao=Subquery(encaminhamentos_ativos.values("prazo_data")[:1]),
            )
            .select_related("atualizado_por")
            .prefetch_related(
                Prefetch(
                    "encaminhamentos",
                    queryset=Encaminhamento.objects.order_by("prazo_data", "data_inicio"),
                    to_attr="encaminhamentos_prefetch",
                )
            ).order_by("-possui_ativo", "prazo_ativo_ordenacao", "-atualizado_em")
        )
        termo = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        ordem_prazo = (self.request.GET.get("ordem_prazo") or "").strip()
        arquivo_morto = (self.request.GET.get("arquivo_morto") or "").strip().lower()
        sort_by = (self.request.GET.get("sort_by") or "").strip()
        sort_dir = (self.request.GET.get("sort_dir") or "asc").strip().lower()
        if sort_dir not in {"asc", "desc"}:
            sort_dir = "asc"
        col_sei = (self.request.GET.get("col_sei") or "").strip()
        col_assunto = (self.request.GET.get("col_assunto") or "").strip()
        col_origem = (self.request.GET.get("col_origem") or "").strip()
        col_destino = (self.request.GET.get("col_destino") or "").strip()
        col_ativos = (self.request.GET.get("col_ativos") or "").strip()
        col_prazo = (self.request.GET.get("col_prazo") or "").strip()
        col_atualizado = (self.request.GET.get("col_atualizado") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(numero_sei__icontains=termo)
                | Q(assunto__icontains=termo)
                | Q(caixa_origem__icontains=termo)
                | Q(encaminhamentos__destino__icontains=termo)
            ).distinct()
        if status in {Processo.Status.EM_ABERTO, Processo.Status.CONCLUIDO}:
            queryset = queryset.filter(status=status)
        if arquivo_morto in {"1", "true", "sim"}:
            queryset = queryset.filter(arquivo_morto=True)
        else:
            queryset = queryset.filter(arquivo_morto=False)
        if col_sei:
            queryset = queryset.filter(numero_sei__icontains=col_sei)
        if col_assunto:
            queryset = queryset.filter(assunto__icontains=col_assunto)
        if col_origem:
            queryset = queryset.filter(caixa_origem__icontains=col_origem)
        if col_destino:
            destino_normalizado = col_destino.lower()
            if "sem encaminhamento" in destino_normalizado:
                queryset = queryset.filter(possui_ativo=False)
            else:
                queryset = queryset.filter(
                    encaminhamentos__data_conclusao__isnull=True,
                    encaminhamentos__destino__icontains=col_destino,
                ).distinct()
        if col_ativos:
            queryset = queryset.annotate(
                ativos_count=Count("encaminhamentos", filter=Q(encaminhamentos__data_conclusao__isnull=True))
            )
            if col_ativos.isdigit():
                queryset = queryset.filter(ativos_count=int(col_ativos))
        if col_prazo:
            if col_prazo == "-":
                queryset = queryset.filter(prazo_ativo_ordenacao__isnull=True)
            elif len(col_prazo) == 10:
                try:
                    data_prazo = datetime.strptime(col_prazo, "%d/%m/%Y").date()
                    queryset = queryset.filter(prazo_ativo_ordenacao=data_prazo)
                except ValueError:
                    pass
            elif len(col_prazo) == 7 and col_prazo[2] == "/":
                try:
                    mes = int(col_prazo[:2])
                    ano = int(col_prazo[3:])
                    queryset = queryset.filter(prazo_ativo_ordenacao__month=mes, prazo_ativo_ordenacao__year=ano)
                except ValueError:
                    pass
            elif len(col_prazo) == 4 and col_prazo.isdigit():
                queryset = queryset.filter(prazo_ativo_ordenacao__year=int(col_prazo))
        if col_atualizado:
            if len(col_atualizado) == 10:
                try:
                    data_atualizado = datetime.strptime(col_atualizado, "%d/%m/%Y").date()
                    queryset = queryset.filter(atualizado_em__date=data_atualizado)
                except ValueError:
                    pass
            elif len(col_atualizado) == 7 and col_atualizado[2] == "/":
                try:
                    mes = int(col_atualizado[:2])
                    ano = int(col_atualizado[3:])
                    queryset = queryset.filter(atualizado_em__month=mes, atualizado_em__year=ano)
                except ValueError:
                    pass
            elif len(col_atualizado) == 4 and col_atualizado.isdigit():
                queryset = queryset.filter(atualizado_em__year=int(col_atualizado))
        if ordem_prazo == "prazo_mais_proximo":
            hoje_local = timezone.localdate()
            diferenca_prazo_subquery = (
                Encaminhamento.objects.filter(
                    processo_id=OuterRef("pk"),
                    data_conclusao__isnull=True,
                )
                .order_by("prazo_data", "data_inicio")
                .annotate(
                    diff_dias=Func(
                        F("prazo_data"),
                        Value(hoje_local),
                        function="DATEDIFF",
                        output_field=IntegerField(),
                    )
                )
                .values("diff_dias")[:1]
            )
            queryset = queryset.annotate(
                diferenca_prazo_hoje=Subquery(
                    diferenca_prazo_subquery,
                    output_field=IntegerField(),
                )
            ).order_by("-possui_ativo", "diferenca_prazo_hoje", "prazo_ativo_ordenacao", "-atualizado_em")
        elif ordem_prazo == "prazo_mais_distante":
            hoje_local = timezone.localdate()
            diferenca_prazo_subquery = (
                Encaminhamento.objects.filter(
                    processo_id=OuterRef("pk"),
                    data_conclusao__isnull=True,
                )
                .order_by("prazo_data", "data_inicio")
                .annotate(
                    diff_dias=Func(
                        F("prazo_data"),
                        Value(hoje_local),
                        function="DATEDIFF",
                        output_field=IntegerField(),
                    )
                )
                .values("diff_dias")[:1]
            )
            queryset = queryset.annotate(
                diferenca_prazo_hoje=Subquery(
                    diferenca_prazo_subquery,
                    output_field=IntegerField(),
                )
            ).order_by("-possui_ativo", "-diferenca_prazo_hoje", "-prazo_ativo_ordenacao", "-atualizado_em")
        if sort_by:
            if sort_by == "sei":
                campo_ordem = "numero_sei"
            elif sort_by == "assunto":
                campo_ordem = "assunto"
            elif sort_by == "origem":
                campo_ordem = "caixa_origem"
            elif sort_by == "destino":
                queryset = queryset.annotate(
                    destino_ativo_ordenacao=Subquery(encaminhamentos_ativos.values("destino")[:1])
                )
                campo_ordem = "destino_ativo_ordenacao"
            elif sort_by == "ativos":
                queryset = queryset.annotate(
                    ativos_count=Count(
                        "encaminhamentos",
                        filter=Q(encaminhamentos__data_conclusao__isnull=True),
                    )
                )
                campo_ordem = "ativos_count"
            elif sort_by == "prazo":
                campo_ordem = "prazo_ativo_ordenacao"
            elif sort_by == "atualizado":
                campo_ordem = "atualizado_em"
            else:
                campo_ordem = ""
            if campo_ordem:
                prefixo = "-" if sort_dir == "desc" else ""
                queryset = queryset.order_by(f"{prefixo}{campo_ordem}", "-atualizado_em")
        return queryset

    def get_context_data(self, **kwargs):
        """Enriquece contexto da listagem com métricas de prazo por processo.

        Regras de negócio:
        - quando há encaminhamento ativo, calcula faixa de risco (`safe/warning/danger`);
        - quando não há ativo, considera processo concluído visualmente.
        """

        context = super().get_context_data(**kwargs)
        active_aba = self._get_aba_ativa()
        view_mode = self.request.GET.get("view") or "cards"
        context["view_mode"] = "table" if view_mode == "table" else "cards"
        context["active_aba"] = active_aba
        context["query"] = (self.request.GET.get("q") or "").strip()
        context["status_filter"] = (self.request.GET.get("status") or "").strip()
        context["ordem_prazo"] = (self.request.GET.get("ordem_prazo") or "").strip()
        context["arquivo_morto_filter"] = (self.request.GET.get("arquivo_morto") or "").strip().lower()
        context["sort_by"] = (self.request.GET.get("sort_by") or "").strip()
        context["sort_dir"] = (self.request.GET.get("sort_dir") or "asc").strip().lower()
        context["col_sei"] = (self.request.GET.get("col_sei") or "").strip()
        context["col_assunto"] = (self.request.GET.get("col_assunto") or "").strip()
        context["col_origem"] = (self.request.GET.get("col_origem") or "").strip()
        context["col_destino"] = (self.request.GET.get("col_destino") or "").strip()
        context["col_ativos"] = (self.request.GET.get("col_ativos") or "").strip()
        context["col_prazo"] = (self.request.GET.get("col_prazo") or "").strip()
        context["col_atualizado"] = (self.request.GET.get("col_atualizado") or "").strip()
        context["total_processos"] = context.get("paginator").count if context.get("paginator") else len(context["processos"])
        context["querystring"] = self._querystring_without_page()
        context["novo_processo_url"] = f"{reverse('lousa_digital_create')}?aba={active_aba}"
        context["abas_lousa"] = self._montar_abas_contexto(
            arquivo_morto=context["arquivo_morto_filter"] in {"1", "true", "sim"},
        )

        for processo in context["processos"]:
            if processo.atualizado_por:
                nome_base = (
                    processo.atualizado_por.get_full_name()
                    or processo.atualizado_por.username
                    or ""
                )
                processo.atualizado_por_nome_curto = _nome_duas_primeiras_partes(nome_base) or "Sistema"
            else:
                processo.atualizado_por_nome_curto = "Sistema"

            encaminhamentos = list(getattr(processo, "encaminhamentos_prefetch", []))
            ativos_list = [item for item in encaminhamentos if item.data_conclusao is None]
            ativos_list.sort(key=lambda item: (item.prazo_limite, item.data_inicio, item.id))
            for enc in ativos_list:
                dados_enc = _dados_prazo(enc)
                alerta_prazo = _dados_alerta_prazo(dados_enc)
                enc.progress_inicio_iso = dados_enc["inicio_iso"]
                enc.progress_total_days = dados_enc["total_dias"]
                enc.progress_atrasado = dados_enc["atrasado"]
                enc.prazo_consumido = dados_enc["consumido"]
                enc.prazo_consumido_fmt = dados_enc["consumido_fmt"]
                enc.prazo_restante_fmt = dados_enc["restante_dias_fmt"]
                enc.progress_alerta_exibir = alerta_prazo["exibir"]
                enc.progress_alerta_texto = alerta_prazo["texto"]
                enc.progress_alerta_classe = alerta_prazo["classe"]
                enc.progress_alerta_posicao = alerta_prazo["posicao"]
                if dados_enc["consumido"] > 75:
                    enc.progress_class = "is-danger"
                elif dados_enc["consumido"] > 50:
                    enc.progress_class = "is-warning"
                else:
                    enc.progress_class = "is-safe"

            processo.encaminhamentos_ativos_card = ativos_list
            ativo = min(ativos_list, key=lambda item: item.prazo_limite) if ativos_list else None
            processo.encaminhamento_monitorado = ativo
            if ativo:
                dados = _dados_prazo(ativo)
                processo.prazo_consumido = dados["consumido"]
                processo.prazo_restante_fmt = dados["restante_dias_fmt"]
                processo.prazo_total_fmt = dados["total_fmt"]
                processo.destino_ativo = ativo.destino
                processo.prazo_data_ativo = ativo.prazo_data
                processo.local_atual = ativo.destino
                processo.encaminhamento_ativo_id = ativo.pk
                processo.progress_inicio_iso = dados["inicio_iso"]
                processo.progress_total_days = dados["total_dias"]
                processo.progress_atrasado = dados["atrasado"]
                processo.prazo_consumido_fmt = dados["consumido_fmt"]
                if dados["consumido"] > 75:
                    processo.progress_class = "is-danger"
                elif dados["consumido"] > 50:
                    processo.progress_class = "is-warning"
                else:
                    processo.progress_class = "is-safe"
            else:
                processo.prazo_consumido = 100
                processo.prazo_restante_fmt = "-"
                processo.prazo_total_fmt = "-"
                processo.destino_ativo = "Sem encaminhamento ativo"
                processo.prazo_data_ativo = None
                processo.local_atual = processo.caixa_origem
                processo.encaminhamento_ativo_id = None
                processo.progress_inicio_iso = ""
                processo.progress_total_days = 0
                processo.progress_atrasado = False
                processo.prazo_consumido_fmt = "0,00"
                processo.progress_class = "is-complete"

            processo.total_encaminhamentos = len(encaminhamentos)
            processo.ativos = len(ativos_list)

        return context

    def _montar_abas_contexto(self, arquivo_morto=False):
        """Monta links e contadores das abas da lousa."""

        contagens = _contagem_processos_por_aba(self.request.user, arquivo_morto=arquivo_morto)
        params = self.request.GET.copy()
        if "aba" in params:
            params.pop("aba")
        if "page" in params:
            params.pop("page")
        sufixo = params.urlencode()
        abas = []
        for aba in LOUSA_ABAS:
            querystring = f"aba={aba}"
            if sufixo:
                querystring = f"{querystring}&{sufixo}"
            abas.append(
                {
                    "nome": aba,
                    "total": contagens.get(aba, 0),
                    "ativa": aba == self._get_aba_ativa(),
                    "url": f"{reverse('lousa_digital_list')}?{querystring}",
                }
            )
        return abas

    def _querystring_without_page(self):
        """Remove parâmetro `page` para preservar filtros ao paginar/navegar."""

        params = self.request.GET.copy()
        if "page" in params:
            params.pop("page")
        encoded = params.urlencode()
        return f"&{encoded}" if encoded else ""


class ProcessoDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard analítico da Lousa Digital."""

    template_name = "lousa_digital/dashboard.html"

    def _get_aba_ativa(self):
        """Retorna a aba atualmente selecionada no dashboard."""

        return _aba_lousa_ativa(self.request.GET.get("aba"))

    def _montar_abas_contexto(self, active_aba):
        """Monta links e contadores das abas para o dashboard."""

        contagens = _contagem_processos_por_aba(self.request.user, arquivo_morto=False)
        abas = []
        for aba in LOUSA_ABAS:
            abas.append(
                {
                    "nome": aba,
                    "total": contagens.get(aba, 0),
                    "ativa": aba == active_aba,
                    "url": f"{reverse('lousa_digital_dashboard')}?aba={aba}",
                }
            )
        return abas

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_aba = self._get_aba_ativa()
        processos_base = (
            _processos_visiveis_para_usuario(self.request.user)
            .filter(caixa_origem=active_aba)
            .select_related("criado_por", "atualizado_por")
            .prefetch_related("encaminhamentos")
        )
        encaminhamentos_base = Encaminhamento.objects.filter(processo__in=processos_base).select_related(
            "processo",
            "criado_por",
            "concluido_por",
        )
        eventos_alerta = EventoTimeline.objects.filter(
            processo__in=processos_base,
            tipo=EventoTimeline.Tipo.EMAIL_72H_ENVIADO,
        )

        processos_lista = list(processos_base)
        encaminhamentos_ativos = list(
            encaminhamentos_base.filter(data_conclusao__isnull=True).order_by(
                "processo_id",
                "prazo_data",
                "data_inicio",
                "id",
            )
        )

        atual_por_processo = {}
        for encaminhamento in encaminhamentos_ativos:
            atual_por_processo.setdefault(encaminhamento.processo_id, encaminhamento)

        processos_destino_atual = Counter()
        processos_criticos = 0
        for processo in processos_lista:
            encaminhamento_atual = atual_por_processo.get(processo.id)
            if encaminhamento_atual is None:
                processos_destino_atual["Sem encaminhamento ativo"] += 1
                continue
            processos_destino_atual[encaminhamento_atual.destino or "Destino não informado"] += 1
            faixa_key, _ = _faixa_prazo_dashboard(encaminhamento_atual.prazo_data)
            if faixa_key in {"vencidos", "vence_hoje", "ate_3"}:
                processos_criticos += 1

        faixas_ordem = [
            ("vencidos", "Vencidos"),
            ("vence_hoje", "Vence hoje"),
            ("ate_3", "1-3 dias"),
            ("ate_7", "4-7 dias"),
            ("acima_7", "Acima de 7 dias"),
        ]
        encaminhamentos_por_faixa = Counter()
        for encaminhamento in encaminhamentos_ativos:
            faixa_key, faixa_label = _faixa_prazo_dashboard(encaminhamento.prazo_data)
            encaminhamentos_por_faixa[(faixa_key, faixa_label)] += 1

        total_processos = len(processos_lista)
        total_processos_com_ativo = len(atual_por_processo)
        percentual_critico = round(
            (processos_criticos / total_processos_com_ativo) * 100,
            1,
        ) if total_processos_com_ativo else 0

        destinos_mais_utilizados = list(
            encaminhamentos_base.values("destino")
            .annotate(total=Count("id"))
            .order_by("-total", "destino")[:10]
        )

        ranking_cadastro_raw = list(
            processos_base.filter(criado_por__isnull=False)
            .values("criado_por_id")
            .annotate(total=Count("id"))
            .order_by("-total", "criado_por_id")[:10]
        )
        ranking_cadastro_ids = [item["criado_por_id"] for item in ranking_cadastro_raw]
        usuarios_cadastro = User.objects.filter(id__in=ranking_cadastro_ids)
        usuarios_cadastro_por_id = {usuario.id: usuario for usuario in usuarios_cadastro}
        ranking_cadastro = [
            {
                "nome": _nome_usuario_dashboard(usuarios_cadastro_por_id.get(item["criado_por_id"])),
                "total": item["total"],
            }
            for item in ranking_cadastro_raw
            if usuarios_cadastro_por_id.get(item["criado_por_id"])
        ]

        context.update(
            {
                "total_processos_monitorados": total_processos,
                "total_processos_com_destino_ativo": total_processos_com_ativo,
                "processos_criticos": processos_criticos,
                "percentual_critico": _formatar_percentual_ptbr(percentual_critico),
                "total_alertas_enviados": eventos_alerta.count(),
                "grafico_processos_destino_atual": {
                    "labels": list(processos_destino_atual.keys()),
                    "values": list(processos_destino_atual.values()),
                },
                "grafico_encaminhamentos_faixa_prazo": {
                    "labels": [label for _, label in faixas_ordem],
                    "values": [encaminhamentos_por_faixa.get((key, label), 0) for key, label in faixas_ordem],
                },
                "grafico_processos_criados_periodo": _serie_diaria_ultimos_30_dias(processos_base, "criado_em"),
                "grafico_encaminhamentos_criados_periodo": _serie_diaria_ultimos_30_dias(
                    encaminhamentos_base, "data_inicio"
                ),
                "grafico_devolucoes_periodo": _serie_diaria_ultimos_30_dias(
                    encaminhamentos_base.filter(data_conclusao__isnull=False),
                    "data_conclusao",
                ),
                "grafico_destinos_mais_recebem": {
                    "labels": [item["destino"] or "Destino não informado" for item in destinos_mais_utilizados],
                    "values": [item["total"] for item in destinos_mais_utilizados],
                },
                "ranking_cadastro": ranking_cadastro,
                "active_aba": active_aba,
                "abas_lousa_dashboard": self._montar_abas_contexto(active_aba),
            }
        )
        return context

class ProcessoCreateView(LoginRequiredMixin, CreateView):
    """Fluxo HTTP de criação de processo na lousa."""

    model = Processo
    form_class = ProcessoForm
    template_name = "lousa_digital/processo_form.html"

    def _get_aba_ativa(self):
        """Retorna a aba selecionada para o cadastro do processo."""

        return _aba_lousa_ativa(self.request.GET.get("aba"))

    def get_initial(self):
        """Preenche a origem automaticamente a partir da aba ativa."""

        initial = super().get_initial()
        initial["caixa_origem"] = self._get_aba_ativa()
        return initial

    def get_form_kwargs(self):
        """Entrega ao formulário a origem fixa resolvida pela aba."""

        kwargs = super().get_form_kwargs()
        kwargs["origem_fixa"] = self._get_aba_ativa()
        return kwargs

    def form_valid(self, form):
        """Aplica metadados de autoria/grupo e registra evento de criação."""

        response = super().form_valid(form)
        self.object.atualizado_por = self.request.user
        self.object.criado_por = self.request.user
        self.object.grupo_insercao = self.request.user.groups.order_by("name", "id").first()
        self.object.save(update_fields=["atualizado_por", "criado_por", "grupo_insercao", "atualizado_em"])
        _registrar_evento(
            self.object,
            EventoTimeline.Tipo.PROCESSO_CRIADO,
            "Processo cadastrado na Lousa Digital.",
            usuario=self.request.user,
        )
        messages.success(self.request, "Processo criado com sucesso.")
        return response

    def get_success_url(self):
        """Redireciona para detalhe do processo recém-criado."""

        return reverse("lousa_digital_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """Expõe metadados da aba ativa para a tela de formulário."""

        context = super().get_context_data(**kwargs)
        active_aba = self._get_aba_ativa()
        context["active_aba"] = active_aba
        context["processo_origem_exibicao"] = active_aba
        context["voltar_lousa_url"] = f"{reverse('lousa_digital_list')}?aba={active_aba}"
        return context


class ProcessoUpdateView(LoginRequiredMixin, UpdateView):
    """Fluxo HTTP de edição de processo existente."""

    model = Processo
    form_class = ProcessoForm
    template_name = "lousa_digital/processo_form.html"

    def get_form_kwargs(self):
        """Mantém a origem atual do processo mesmo com campo oculto."""

        kwargs = super().get_form_kwargs()
        kwargs["origem_fixa"] = self.get_object().caixa_origem
        return kwargs

    def get_queryset(self):
        """Restringe edição ao conjunto de processos visíveis ao usuário."""

        return _processos_visiveis_para_usuario(self.request.user)

    def form_valid(self, form):
        """Atualiza metadado de autor da alteração e registra evento de edição."""

        arquivo_morto_antes = Processo.objects.filter(pk=form.instance.pk).values_list("arquivo_morto", flat=True).first()
        response = super().form_valid(form)
        self.object.atualizado_por = self.request.user
        self.object.save(update_fields=["atualizado_por", "atualizado_em"])
        _registrar_evento(
            self.object,
            EventoTimeline.Tipo.PROCESSO_EDITADO,
            "Dados do processo atualizados.",
            usuario=self.request.user,
        )
        if (arquivo_morto_antes is False) and self.object.arquivo_morto:
            ja_tem_evento_arquivo_morto = EventoTimeline.objects.filter(
                processo=self.object,
                descricao__icontains="arquivo morto",
            ).exists()
            if not ja_tem_evento_arquivo_morto:
                _registrar_evento(
                    self.object,
                    EventoTimeline.Tipo.PROCESSO_EDITADO,
                    "Enviado para arquivo morto.",
                    usuario=self.request.user,
                )
        messages.success(self.request, "Processo atualizado.")
        return response

    def get_success_url(self):
        """Redireciona para detalhe após atualização."""

        return reverse("lousa_digital_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """Expõe a origem do processo como informação somente leitura."""

        context = super().get_context_data(**kwargs)
        origem = self.object.caixa_origem
        aba = Processo.normalizar_aba_origem(origem, default="")
        context["active_aba"] = aba
        context["processo_origem_exibicao"] = origem or "-"
        context["voltar_lousa_url"] = (
            f"{reverse('lousa_digital_list')}?aba={aba}" if aba else reverse("lousa_digital_list")
        )
        return context


class ProcessoDeleteView(LoginRequiredMixin, DeleteView):
    """Fluxo HTTP de exclusão de processo."""

    model = Processo
    template_name = "lousa_digital/processo_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        """Bloqueia exclusão de processos via interface da Lousa Digital."""

        messages.error(request, "Exclusão de processos está desabilitada na Lousa Digital.")
        return redirect("lousa_digital_detail", pk=kwargs["pk"])

    def get_queryset(self):
        """Restringe exclusão ao escopo de visibilidade do usuário."""

        return _processos_visiveis_para_usuario(self.request.user)

    def get_success_url(self):
        """Exibe feedback e retorna para listagem após exclusão."""

        messages.success(self.request, "Processo excluido com sucesso.")
        return reverse("lousa_digital_list")


class ProcessoDetailView(LoginRequiredMixin, DetailView):
    """Exibe detalhe do processo com encaminhamentos e timeline consolidada."""

    model = Processo
    template_name = "lousa_digital/processo_detail.html"
    context_object_name = "processo"

    def get_queryset(self):
        """Carrega processo com relacionamentos necessários para tela de detalhe.

        ORM:
        - `select_related` para usuário de atualização;
        - `Prefetch` de encaminhamentos e eventos com usuários para evitar N+1.
        """

        return (
            _processos_visiveis_para_usuario(self.request.user)
            .select_related("atualizado_por")
            .prefetch_related(
                Prefetch(
                    "encaminhamentos",
                    queryset=Encaminhamento.objects.select_related("criado_por", "concluido_por").order_by("-data_inicio"),
                ),
                "eventos__usuario",
            )
            .all()
        )

    def get_context_data(self, **kwargs):
        """Monta formulários auxiliares e calcula dados de prazo por encaminhamento."""

        context = super().get_context_data(**kwargs)
        processo = context["processo"]
        context["processo_arquivo_morto"] = processo.arquivo_morto
        encaminhamento_form = EncaminhamentoForm()
        encaminhamento_form.fields["email_notificacao"].widget.attrs["list"] = "email-notificacao-opcoes"
        context["encaminhamento_form"] = encaminhamento_form
        context["setores_destino_disponiveis"] = encaminhamento_form.setores_disponiveis
        context["nota_form"] = NotaTimelineForm()
        context["eventos"] = processo.eventos.select_related("usuario", "encaminhamento")
        context["emails_notificacao_sugeridos"] = list(
            Encaminhamento.objects.exclude(email_notificacao__isnull=True)
            .exclude(email_notificacao="")
            .order_by("email_notificacao")
            .values_list("email_notificacao", flat=True)
            .distinct()
        )

        encaminhamentos = []
        for enc in processo.encaminhamentos.all():
            dados = _dados_prazo(enc)
            enc.prazo = dados
            encaminhamentos.append(enc)
        context["encaminhamentos"] = encaminhamentos

        ativo = processo.encaminhamento_ativo_prioritario()
        context["encaminhamento_monitorado"] = ativo
        aba = Processo.normalizar_aba_origem(processo.caixa_origem, default="")
        context["voltar_lousa_url"] = f"{reverse('lousa_digital_list')}?aba={aba}" if aba else reverse("lousa_digital_list")
        context["editar_processo_url"] = (
            f"{reverse('lousa_digital_update', kwargs={'pk': processo.pk})}?aba={aba}"
            if aba
            else reverse("lousa_digital_update", kwargs={"pk": processo.pk})
        )
        return context


class CriarEncaminhamentoView(LoginRequiredMixin, View):
    """Recebe POST para abrir novo encaminhamento de um processo."""

    def post(self, request, pk):
        """Valida formulário, cria encaminhamento e mantém processo em aberto."""

        processo = get_object_or_404(_processos_visiveis_para_usuario(request.user), pk=pk)
        if processo.arquivo_morto:
            messages.error(
                request,
                "Processo em arquivo morto não pode receber novos encaminhamentos.",
            )
            return redirect("lousa_digital_detail", pk=pk)

        form = EncaminhamentoForm(request.POST)
        if not form.is_valid():
            messages.error(request, form.errors.as_text())
            return redirect("lousa_digital_detail", pk=pk)

        encaminhamento = form.save(commit=False)
        encaminhamento.processo = processo
        encaminhamento.criado_por = request.user
        encaminhamento.save()

        processo.status = Processo.Status.EM_ABERTO
        processo.atualizado_por = request.user
        processo.save(update_fields=["status", "atualizado_por", "atualizado_em"])

        _registrar_evento(
            processo,
            EventoTimeline.Tipo.ENCAMINHAMENTO_CRIADO,
            (
                f"Encaminhado para {encaminhamento.destino} com prazo de "
                f"{encaminhamento.prazo_data.strftime('%d/%m/%Y')}."
            ),
            usuario=request.user,
            encaminhamento=encaminhamento,
        )
        messages.success(request, "Encaminhamento registrado.")
        return redirect("lousa_digital_detail", pk=pk)


class DevolverEncaminhamentoView(LoginRequiredMixin, View):
    """Recebe POST para devolver/concluir encaminhamento ativo."""

    def post(self, request, pk, encaminhamento_id):
        """Conclui encaminhamento, registra evento e recalcula status do processo."""

        processo = get_object_or_404(_processos_visiveis_para_usuario(request.user), pk=pk)
        encaminhamento = get_object_or_404(
            Encaminhamento,
            pk=encaminhamento_id,
            processo_id=processo.pk,
        )

        if not encaminhamento.marcar_devolvido(request.user):
            messages.info(request, "Este encaminhamento ja estava devolvido.")
            return redirect("lousa_digital_detail", pk=pk)

        _registrar_evento(
            processo,
            EventoTimeline.Tipo.ENCAMINHAMENTO_DEVOLVIDO,
            (
                f"Encaminhamento ({processo.caixa_origem} - {encaminhamento.destino}) "
                f"devolvido em {timezone.localtime(encaminhamento.data_conclusao).strftime('%d/%m/%Y %H:%M')}."
            ),
            usuario=request.user,
            encaminhamento=encaminhamento,
        )

        processo.atualizar_status_por_encaminhamentos()

        messages.success(request, "Encaminhamento devolvido com sucesso.")
        return redirect("lousa_digital_detail", pk=pk)


class CriarNotaView(LoginRequiredMixin, View):
    """Recebe POST para registrar nota livre na timeline do processo."""

    def post(self, request, pk):
        """Valida nota, registra evento e atualiza metadado de edição do processo."""

        processo = get_object_or_404(_processos_visiveis_para_usuario(request.user), pk=pk)
        form = NotaTimelineForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe o texto da nota.")
            return redirect("lousa_digital_detail", pk=pk)

        _registrar_evento(
            processo,
            EventoTimeline.Tipo.NOTA,
            form.cleaned_data["descricao"],
            usuario=request.user,
        )
        processo.atualizado_por = request.user
        processo.save(update_fields=["atualizado_por", "atualizado_em"])
        messages.success(request, "Nota registrada na timeline.")
        return redirect("lousa_digital_detail", pk=pk)
