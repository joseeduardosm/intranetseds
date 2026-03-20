"""
Views do app `sala_situacao` (HTML + endpoints JSON auxiliares).

Este módulo orquestra os fluxos HTTP de:
- navegação hierárquica entre indicadores, processos e entregas;
- CRUD das entidades do domínio;
- monitoramento por ciclos/variáveis;
- recursos auxiliares para interface (sugestões, marcadores e dados de gráficos).

Integração com arquitetura Django:
- usa `forms.py` para validação de regras de negócio;
- consulta `models.py` com filtros ORM e operações transacionais;
- aplica autenticação/permissões nativas e regras de `access.py`;
- renderiza templates server-side e responde APIs leves em JSON.
"""

import re
import json
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Value, IntegerField, Case, When
from django.db.models.functions import Coalesce
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, Http404, JsonResponse, HttpResponseNotAllowed
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, RedirectView, TemplateView, UpdateView

from auditoria.models import AuditLog
from usuarios.models import SetorNode
from usuarios.permissions import ADMIN_GROUP_NAME
from .access import (
    user_has_sala_situacao_access,
    user_is_monitoring_group_member,
    visible_group_ids_for_user,
)

from .forms import (
    EntregaForm,
    IndicadorEstrategicoForm,
    IndicadorTaticoForm,
    IndicadorVariavelForm,
    MonitoramentoEntregaForm,
    NotaItemForm,
    ProcessoForm,
)
from .models import (
    Entrega,
    IndicadorVariavelCicloMonitoramento,
    IndicadorEstrategico,
    IndicadorTatico,
    IndicadorVariavel,
    IndicadorCicloValor,
    Marcador,
    MarcadorVinculoAutomaticoGrupoItem,
    MarcadorVinculoItem,
    NotaItem,
    Processo,
    escolher_cor_marcador,
    normalizar_nome_marcador,
)


_CICLO_NOME_RE = re.compile(r"\bCiclo\s+(\d+)\b", re.IGNORECASE)


def _reverse_sala_route(request, route_name, **kwargs):
    """Resolve nomes de rota do legado no prefixo antigo quando necessário."""

    resolver_match = getattr(request, "resolver_match", None)
    route_candidates = [route_name]

    if route_name.startswith("sala_"):
        url_name = getattr(resolver_match, "url_name", "") or ""
        view_name = getattr(resolver_match, "view_name", "") or ""
        if url_name.startswith("sala_old_") or view_name.startswith("sala_old_"):
            route_candidates.insert(0, f"sala_old_{route_name[5:]}")

    for candidate in route_candidates:
        try:
            return reverse(candidate, **kwargs)
        except NoReverseMatch:
            continue

    return reverse(route_name, **kwargs)


def _extrair_numero_ciclo_por_nome(nome):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `nome`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not nome:
        return None
    match = _CICLO_NOME_RE.search(nome)
    if not match:
        return None
    return int(match.group(1))


def ordenar_entregas_por_ciclo(queryset):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `queryset`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    entregas = list(queryset)
    entregas.sort(
        key=lambda entrega: (
            (
                entrega.ciclo_monitoramento.numero
                if getattr(entrega, "ciclo_monitoramento_id", None)
                else _extrair_numero_ciclo_por_nome(entrega.nome)
            )
            is None,
            (
                entrega.ciclo_monitoramento.numero
                if getattr(entrega, "ciclo_monitoramento_id", None)
                else _extrair_numero_ciclo_por_nome(entrega.nome)
            )
            or 0,
            (entrega.nome or "").lower(),
        )
    )
    return entregas


def _usuario_admin_sala(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `user`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=ADMIN_GROUP_NAME).exists()


def _user_can_update_indicator(user, indicador):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not getattr(user, "is_authenticated", False):
        return False
    meta = indicador._meta
    if not user.has_perm(f"{meta.app_label}.change_{meta.model_name}"):
        return False
    if _usuario_admin_sala(user):
        return True
    return bool(getattr(indicador, "criado_por_id", None) and indicador.criado_por_id == user.id)


def _user_can_delete_indicator(user, indicador):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not getattr(user, "is_authenticated", False):
        return False
    meta = indicador._meta
    if not user.has_perm(f"{meta.app_label}.delete_{meta.model_name}"):
        return False
    if _usuario_admin_sala(user):
        return True
    return bool(getattr(indicador, "criado_por_id", None) and indicador.criado_por_id == user.id)


def _user_can_monitorar_entrega(user, entrega):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not getattr(user, "is_authenticated", False):
        return False
    if user.has_perm("sala_situacao.change_entrega") or _usuario_admin_sala(user):
        return True
    if not (user.has_perm("sala_situacao.monitorar_entrega") or user_is_monitoring_group_member(user)):
        return False
    if not (entrega and entrega.eh_entrega_monitoramento and entrega.variavel_monitoramento_id):
        return False
    grupos_usuario_ids = set(user.groups.values_list("id", flat=True))
    grupos_variavel_ids = set(entrega.variavel_monitoramento.grupos_monitoramento.values_list("id", flat=True))
    return bool(grupos_usuario_ids.intersection(grupos_variavel_ids))


def _percentual_seguro(valor):
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _chart_compare_payload(item):
    snapshot = item.progresso_snapshot
    if isinstance(snapshot, dict):
        prazo = snapshot.get("prazo_percentual", 0)
        conclusao = snapshot.get("conclusao_percentual", 0)
        conclusao_label = snapshot.get("titulo_conclusao", "Conclusao")
    else:
        prazo = getattr(snapshot, "prazo_percentual", 0)
        conclusao = getattr(snapshot, "conclusao_percentual", 0)
        conclusao_label = getattr(snapshot, "titulo_conclusao", "Conclusao")
    return {
        "type": "bar_compare",
        "prazo": _percentual_seguro(prazo),
        "conclusao": _percentual_seguro(conclusao),
        "conclusao_label": conclusao_label,
    }


def _build_indicator_series_map(indicadores):
    indicadores = [item for item in (indicadores or []) if item]
    if not indicadores:
        return {}

    ct_ie = ContentType.objects.get_for_model(IndicadorEstrategico)
    ct_it = ContentType.objects.get_for_model(IndicadorTatico)
    ids_ie = [item.pk for item in indicadores if isinstance(item, IndicadorEstrategico)]
    ids_it = [item.pk for item in indicadores if isinstance(item, IndicadorTatico)]
    filtros = Q()
    if ids_ie:
        filtros |= Q(content_type=ct_ie, object_id__in=ids_ie)
    if ids_it:
        filtros |= Q(content_type=ct_it, object_id__in=ids_it)
    if not filtros:
        return {}

    variaveis = list(
        IndicadorVariavel.objects.filter(filtros)
        .order_by("content_type_id", "object_id", "ordem", "id")
    )
    primeira_variavel_por_item = {}
    variaveis_por_id = {}
    for variavel in variaveis:
        chave = (variavel.content_type_id, variavel.object_id)
        primeira_variavel_por_item.setdefault(chave, variavel.id)
        variaveis_por_id[variavel.id] = variavel

    if not primeira_variavel_por_item:
        return {}

    valores = (
        IndicadorCicloValor.objects.select_related("ciclo", "variavel")
        .filter(variavel_id__in=primeira_variavel_por_item.values())
        .order_by("variavel_id", "ciclo__periodo_fim", "atualizado_em", "id")
    )
    por_variavel_ciclo = {}
    for valor in valores:
        chave = (valor.variavel_id, valor.ciclo_id)
        por_variavel_ciclo[chave] = valor

    pontos_por_variavel = defaultdict(list)
    for valor in por_variavel_ciclo.values():
        data_ref = getattr(valor.ciclo, "periodo_fim", None) or timezone.localtime(valor.atualizado_em).date()
        label = data_ref.strftime("%b/%y")
        pontos_por_variavel[valor.variavel_id].append(
            {
                "ordem": data_ref,
                "label": label.title(),
                "valor": round(float(valor.valor), 2),
            }
        )

    series_map = {}
    for chave_item, variavel_id in primeira_variavel_por_item.items():
        pontos = sorted(pontos_por_variavel.get(variavel_id, []), key=lambda item: item["ordem"])[-8:]
        variavel = variaveis_por_id.get(variavel_id)
        series_map[chave_item] = {
            "labels": [ponto["label"] for ponto in pontos],
            "values": [ponto["valor"] for ponto in pontos],
            "unit": getattr(variavel, "unidade_medida", "") or "",
            "label": getattr(variavel, "nome", "Serie"),
        }
    return series_map


def _chart_payload_for_indicator(indicador, series_map):
    compare_payload = _chart_compare_payload(indicador)
    ct = ContentType.objects.get_for_model(indicador.__class__)
    serie = (series_map or {}).get((ct.id, indicador.pk), {})
    labels = serie.get("labels") or []
    values = serie.get("values") or []

    if indicador.tipo_indicador == indicador.TipoIndicador.PROCESSUAL:
        return {
            **compare_payload,
            "badge": "Comparativo compacto",
        }

    if len(values) < 2:
        return {
            **compare_payload,
            "badge": "Fallback sem historico",
        }

    if indicador.tipo_indicador == indicador.TipoIndicador.MATEMATICO_ACUMULATIVO:
        return {
            **compare_payload,
            "badge": "Atingimento acumulado",
        }

    if indicador.tipo_indicador == indicador.TipoIndicador.MATEMATICO:
        return {
            "type": "line_meta",
            "labels": labels,
            "values": values,
            "meta": round(float(indicador.meta_valor or 0), 2),
            "series_label": serie.get("label", "Serie"),
            "unit": serie.get("unit", ""),
            "badge": "Linha com meta",
        }

    return {
        **compare_payload,
        "badge": "Comparativo compacto",
    }


def _entregas_queryset_para_usuario(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `user`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    queryset = Entrega.objects.all()
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if _usuario_admin_sala(user):
        return queryset
    grupos_usuario_ids = list(visible_group_ids_for_user(user))
    if not grupos_usuario_ids:
        return queryset.none()
    content_type_entrega = ContentType.objects.get_for_model(Entrega)
    entregas_ids = MarcadorVinculoAutomaticoGrupoItem.objects.filter(
        content_type=content_type_entrega,
        grupo_id__in=grupos_usuario_ids,
    ).values_list("object_id", flat=True)
    return queryset.filter(id__in=entregas_ids).distinct()


def _processos_queryset_para_usuario(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `user`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    queryset = Processo.objects.all()
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if _usuario_admin_sala(user):
        return queryset
    grupos_usuario_ids = list(visible_group_ids_for_user(user))
    if not grupos_usuario_ids:
        return queryset.none()
    content_type_processo = ContentType.objects.get_for_model(Processo)
    processos_ids = MarcadorVinculoAutomaticoGrupoItem.objects.filter(
        content_type=content_type_processo,
        grupo_id__in=grupos_usuario_ids,
    ).values_list("object_id", flat=True)
    entregas_ids = _entregas_queryset_para_usuario(user).values_list("id", flat=True)
    return queryset.filter(Q(id__in=processos_ids) | Q(entregas__id__in=entregas_ids)).distinct()


def _filtrar_processos_visiveis_para_usuario(queryset, user):
    """Restringe um queryset de processos aos itens visíveis para o usuário."""

    processos_permitidos = _processos_queryset_para_usuario(user).values_list("id", flat=True)
    return queryset.filter(id__in=processos_permitidos).distinct()


def _indicadores_estrategicos_queryset_para_usuario(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação."""

    queryset = IndicadorEstrategico.objects.all()
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.distinct()


def _indicadores_taticos_queryset_para_usuario(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação."""

    queryset = IndicadorTatico.objects.all()
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.distinct()


def _setores_visiveis_para_usuario(user):
    """Executa uma rotina de apoio ao domínio de Sala de Situação."""

    queryset = SetorNode.objects.filter(ativo=True).select_related("group", "parent__group")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if _usuario_admin_sala(user):
        return queryset.order_by("group__name")
    grupos_usuario_ids = list(visible_group_ids_for_user(user))
    if not grupos_usuario_ids:
        return queryset.none()
    return queryset.filter(group_id__in=grupos_usuario_ids).order_by("group__name")


def _setor_ids_com_descendentes(setor_id):
    """Executa uma rotina de apoio ao domínio de Sala de Situação."""

    nodes = list(SetorNode.objects.filter(ativo=True).values("id", "parent_id"))
    children_by_parent = {}
    for node in nodes:
        children_by_parent.setdefault(node["parent_id"], []).append(node["id"])

    pending = [setor_id]
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(children_by_parent.get(current, []))
    return visited


def _filtrar_queryset_por_setor(queryset, model_class, setor_id):
    """Executa uma rotina de apoio ao domínio de Sala de Situação."""

    if not setor_id:
        return queryset
    setor_ids = _setor_ids_com_descendentes(setor_id)
    group_ids = list(
        SetorNode.objects.filter(id__in=setor_ids, ativo=True).values_list("group_id", flat=True)
    )
    content_type = ContentType.objects.get_for_model(model_class)
    object_ids = MarcadorVinculoAutomaticoGrupoItem.objects.filter(
        content_type=content_type,
        grupo_id__in=group_ids,
    ).values_list("object_id", flat=True)
    return queryset.filter(id__in=object_ids).distinct()


def _resolver_cascata_ie(indicador_estrategico):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `indicador_estrategico`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    content_type_ie = ContentType.objects.get_for_model(IndicadorEstrategico)
    indicadores_taticos = IndicadorTatico.objects.none()
    processos_via_it = Processo.objects.filter(indicadores_estrategicos=indicador_estrategico).distinct()
    processos_monitoramento = Processo.objects.filter(
        entregas__variavel_monitoramento__content_type=content_type_ie,
        entregas__variavel_monitoramento__object_id=indicador_estrategico.pk,
    ).distinct()
    processos = (processos_via_it | processos_monitoramento).distinct().order_by("nome")
    processos_ids = list(processos.values_list("id", flat=True))

    entregas_via_processo = Entrega.objects.filter(processos__in=processos_ids).distinct()
    entregas_monitoramento = Entrega.objects.filter(
        variavel_monitoramento__content_type=content_type_ie,
        variavel_monitoramento__object_id=indicador_estrategico.pk,
    ).distinct()
    entregas = (entregas_via_processo | entregas_monitoramento).distinct()
    return {
        "indicadores_estrategicos": IndicadorEstrategico.objects.filter(pk=indicador_estrategico.pk),
        "indicadores_taticos": indicadores_taticos,
        "processos": processos,
        "entregas": entregas,
    }

def _resolver_cascata_it(indicador_tatico):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `indicador_tatico`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    processos = Processo.objects.filter(indicadores_taticos=indicador_tatico).distinct().order_by("nome")
    processos_ids = list(processos.values_list("id", flat=True))

    entregas = Entrega.objects.filter(processos__in=processos_ids).distinct()
    return {
        "indicadores_taticos": IndicadorTatico.objects.filter(pk=indicador_tatico.pk),
        "processos": processos,
        "entregas": entregas,
    }


def _limpar_recursos_genericos_do_indicador(model_class, ids):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not ids:
        return
    content_type = ContentType.objects.get_for_model(model_class)
    IndicadorVariavel.objects.filter(content_type=content_type, object_id__in=ids).delete()
    IndicadorVariavelCicloMonitoramento.objects.filter(
        variavel__content_type=content_type,
        variavel__object_id__in=ids,
    ).delete()
    NotaItem.objects.filter(content_type=content_type, object_id__in=ids).delete()


_MARCADOR_ITEM_TIPO_MAP = {
    "ie": IndicadorEstrategico,
    "indicador-estrategico": IndicadorEstrategico,
    "it": IndicadorTatico,
    "indicador-tatico": IndicadorTatico,
    "processo": Processo,
    "entrega": Entrega,
}


def _resolver_modelo_item_por_tipo(tipo):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `tipo`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    return _MARCADOR_ITEM_TIPO_MAP.get((tipo or "").strip().lower())


def _carregar_item_marcador(tipo, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    model_class = _resolver_modelo_item_por_tipo(tipo)
    if not model_class:
        raise Http404("Tipo de item inválido para marcadores.")
    return model_class.objects.filter(pk=pk).first()


def _verificar_permissao_change_item(request, item):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    meta = item._meta
    return request.user.has_perm(f"{meta.app_label}.change_{meta.model_name}")


@login_required
@require_GET
def marcador_sugestoes_api(request):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `request`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not request.user.has_perm("sala_situacao.change_processo"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    termo = (request.GET.get("q") or "").strip()
    qs = Marcador.objects.filter(ativo=True)
    if termo:
        qs = qs.filter(nome__icontains=termo)
    marcadores = [
        {"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor}
        for marcador in qs.order_by("nome")[:30]
    ]
    return JsonResponse({"results": marcadores})


@login_required
@require_GET
def variavel_sugestoes_api(request):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `request`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not request.user.has_perm("sala_situacao.view_salasituacaopainel"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    termo = (request.GET.get("q") or "").strip()
    somente_ativas = (request.GET.get("somente_ativas") or "").strip().lower() in {"1", "true", "sim", "yes"}
    qs = IndicadorVariavel.objects.select_related("content_type").all()
    if somente_ativas:
        hoje = timezone.localdate()
        ct_ie = ContentType.objects.get_for_model(IndicadorEstrategico)
        ct_it = ContentType.objects.get_for_model(IndicadorTatico)
        ciclos_ativos = IndicadorVariavelCicloMonitoramento.objects.filter(
            variavel_id=OuterRef("id"),
            periodo_inicio__lte=hoje,
            periodo_fim__gte=hoje,
        )
        qs = (
            qs.filter(
                Q(content_type=ct_ie, object_id__in=IndicadorEstrategico.objects.values("id"))
                | Q(content_type=ct_it, object_id__in=IndicadorTatico.objects.values("id"))
            )
            .annotate(em_monitoramento=Exists(ciclos_ativos))
            .filter(em_monitoramento=True)
        )
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(descricao__icontains=termo))

    resultados = []
    for variavel in qs.order_by("nome", "id")[:80]:
        indicador = variavel.indicador
        indicador_label = getattr(indicador, "nome", "-")
        resultados.append(
            {
                "id": variavel.id,
                "nome": variavel.nome,
                "indicador_label": indicador_label,
                "unidade_medida": variavel.unidade_medida,
                "tipo_numerico": variavel.tipo_numerico,
                "content_type": variavel.content_type.model,
                "object_id": variavel.object_id,
            }
        )
    return JsonResponse({"results": resultados})


@login_required
@require_POST
def marcador_criar_api(request):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `request`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not request.user.has_perm("sala_situacao.change_processo"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    nome = (payload.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"detail": "Informe o nome do marcador."}, status=400)
    nome = re.sub(r"\s+", " ", nome)
    nome_normalizado = normalizar_nome_marcador(nome)
    marcador = Marcador.objects.filter(nome_normalizado=nome_normalizado).first()
    if marcador is None:
        marcador = Marcador.objects.create(
            nome=nome,
            nome_normalizado=nome_normalizado,
            cor=escolher_cor_marcador(),
            ativo=True,
        )
    elif marcador.nome != nome:
        marcador.nome = nome
        marcador.save(update_fields=["nome", "nome_normalizado", "atualizado_em"])
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor}, status=201)


@login_required
def marcador_cor_api(request, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if request.method != "PATCH":
        return HttpResponseNotAllowed(["PATCH"])
    if not request.user.has_perm("sala_situacao.change_processo"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    marcador = Marcador.objects.filter(pk=pk, ativo=True).first()
    if not marcador:
        raise Http404("Marcador não encontrado.")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    cor = (payload.get("cor") or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", cor):
        return JsonResponse({"detail": "Cor inválida. Use #RRGGBB."}, status=400)
    marcador.cor = cor
    marcador.save(update_fields=["cor", "atualizado_em"])
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor})


@login_required
def marcador_excluir_api(request, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if request.method != "DELETE":
        return HttpResponseNotAllowed(["DELETE"])
    if not request.user.has_perm("sala_situacao.change_processo"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Payload inválido."}, status=400)
    admin_username = (payload.get("admin_username") or "").strip()
    admin_password = payload.get("admin_password") or ""
    if not admin_username or not admin_password:
        return JsonResponse({"detail": "Informe usuário e senha de admin."}, status=400)
    admin_user = authenticate(request, username=admin_username, password=admin_password)
    if not admin_user or not admin_user.is_staff or not admin_user.is_active:
        return JsonResponse({"detail": "Credenciais administrativas inválidas."}, status=403)
    marcador = Marcador.objects.filter(pk=pk, ativo=True).first()
    if not marcador:
        raise Http404("Marcador não encontrado.")
    marcador.ativo = False
    marcador.save(update_fields=["ativo", "atualizado_em"])
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.UPDATE,
        content_type=ContentType.objects.get_for_model(Marcador),
        object_id=str(marcador.pk),
        object_repr=str(marcador),
        changes={
            "ativo": {"old": True, "new": False},
            "operacao": "inativacao_global_marcador",
            "admin_revalidado": admin_username,
        },
    )
    return JsonResponse({"ok": True})


@login_required
@require_GET
def item_marcadores_api(request, tipo, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    item = _carregar_item_marcador(tipo, pk)
    if not item:
        raise Http404("Item não encontrado.")
    if not _verificar_permissao_change_item(request, item):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    locais = [{"id": m.id, "nome": m.nome, "cor": m.cor} for m in item.marcadores_locais]
    efetivos = [{"id": m.id, "nome": m.nome, "cor": m.cor} for m in item.marcadores_efetivos]
    return JsonResponse({"locais": locais, "efetivos": efetivos})


@login_required
@require_POST
def item_marcador_vincular_api(request, tipo, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    item = _carregar_item_marcador(tipo, pk)
    if not item:
        raise Http404("Item não encontrado.")
    if not _verificar_permissao_change_item(request, item):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    marcador_id = payload.get("marcador_id")
    if not str(marcador_id).isdigit():
        return JsonResponse({"detail": "marcador_id inválido."}, status=400)
    marcador = Marcador.objects.filter(pk=int(marcador_id), ativo=True).first()
    if not marcador:
        return JsonResponse({"detail": "Marcador não encontrado."}, status=404)
    content_type = ContentType.objects.get_for_model(item.__class__)
    MarcadorVinculoItem.objects.get_or_create(
        content_type=content_type,
        object_id=item.pk,
        marcador=marcador,
    )
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor}, status=201)


@login_required
def item_marcador_desvincular_api(request, tipo, pk, marcador_id):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if request.method != "DELETE":
        return HttpResponseNotAllowed(["DELETE"])
    item = _carregar_item_marcador(tipo, pk)
    if not item:
        raise Http404("Item não encontrado.")
    if not _verificar_permissao_change_item(request, item):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    content_type = ContentType.objects.get_for_model(item.__class__)
    MarcadorVinculoItem.objects.filter(
        content_type=content_type,
        object_id=item.pk,
        marcador_id=marcador_id,
    ).delete()
    return JsonResponse({"ok": True})


class SalaSituacaoHomeView(PermissionRequiredMixin, TemplateView):
    """Classe `SalaSituacaoHomeView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    template_name = "sala_situacao/home.html"
    permission_required = "sala_situacao.view_salasituacaopainel"
    raise_exception = True

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return user_has_sala_situacao_access(self.request.user)

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        indicadores_estrategicos = _indicadores_estrategicos_queryset_para_usuario(self.request.user).prefetch_related(
            "marcadores_vinculos__marcador"
        ).order_by("nome")
        indicadores = []
        for indicador in indicadores_estrategicos:
            indicadores.append(
                {
                    "obj": indicador,
                    "detail_url": reverse("sala_indicador_estrategico_detail", kwargs={"pk": indicador.pk}),
                }
            )
        indicadores.sort(key=lambda item: (item["obj"].nome or "").lower())
        series_map = _build_indicator_series_map([item["obj"] for item in indicadores])
        for item in indicadores:
            chart_payload = _chart_payload_for_indicator(item["obj"], series_map)
            item["chart_payload"] = chart_payload
            item["chart_payload_json"] = json.dumps(chart_payload)
        context["indicadores"] = indicadores
        return context


class SalaSituacaoPlotlyCardsMockView(PermissionRequiredMixin, TemplateView):
    """Renderiza um mock visual para validar cards com Plotly na capa."""

    template_name = "sala_situacao/plotly_cards_mock.html"
    permission_required = "sala_situacao.view_salasituacaopainel"
    raise_exception = True

    def has_permission(self):
        return user_has_sala_situacao_access(self.request.user)


class SalaSituacaoIndicadoresRedirectView(PermissionRequiredMixin, RedirectView):
    """Redireciona listagens legadas de indicadores para a home consolidada."""

    pattern_name = "sala_situacao_home"
    permanent = False
    raise_exception = True
    permission_required = "sala_situacao.view_salasituacaopainel"

    def has_permission(self):
        return user_has_sala_situacao_access(self.request.user)


class SalaSituacaoConsolidadoView(PermissionRequiredMixin, TemplateView):
    """Classe `SalaSituacaoConsolidadoView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    template_name = "sala_situacao/painel_consolidado.html"
    permission_required = "sala_situacao.view_salasituacaopainel"
    raise_exception = True
    per_page = 8

    def _paginate(self, queryset, page_param):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        paginator = Paginator(queryset, self.per_page)
        page_number = self.request.GET.get(page_param, 1)
        try:
            return paginator.page(page_number)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    def _querystring_without(self, *keys):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        query_params = self.request.GET.copy()
        for key in keys:
            query_params.pop(key, None)
        return query_params.urlencode()

    def _selected_marcadores(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        bruto = (self.request.GET.get("marcadores") or "").strip()
        if not bruto:
            return []
        return [int(item) for item in bruto.split(",") if item.strip().isdigit()]

    @staticmethod
    def _item_tem_algum_marcador(item, marcadores_ids):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not marcadores_ids:
            return True
        ids_item = {marcador.id for marcador in item.marcadores_efetivos if marcador.ativo}
        return bool(ids_item.intersection(marcadores_ids))

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        marcadores_ids = set(self._selected_marcadores())

        indicadores_estrategicos = IndicadorEstrategico.objects.prefetch_related(
            "marcadores_vinculos__marcador",
        ).order_by("nome")
        indicadores = []
        for indicador in indicadores_estrategicos:
            indicadores.append(
                {
                    "obj": indicador,
                    "detail_url": reverse("sala_indicador_estrategico_detail", kwargs={"pk": indicador.pk}),
                }
            )
        if marcadores_ids:
            indicadores = [
                item
                for item in indicadores
                if self._item_tem_algum_marcador(item["obj"], marcadores_ids)
            ]
        indicadores.sort(key=lambda item: (item["obj"].nome or "").lower())
        series_map = _build_indicator_series_map([item["obj"] for item in indicadores])
        for item in indicadores:
            chart_payload = _chart_payload_for_indicator(item["obj"], series_map)
            item["chart_payload"] = chart_payload
            item["chart_payload_json"] = json.dumps(chart_payload)

        processos_qs = Processo.objects.prefetch_related(
            "indicadores_estrategicos",
            "entregas",
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
        ).order_by("nome")
        processos = [
            processo
            for processo in processos_qs
            if self._item_tem_algum_marcador(processo, marcadores_ids)
        ]
        entregas_qs = Entrega.objects.select_related(
            "ciclo_monitoramento",
            "variavel_monitoramento",
        ).prefetch_related(
            "processos",
            "marcadores_vinculos__marcador",
            "processos__marcadores_vinculos__marcador",
            "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
            "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
        ).order_by("nome")
        entregas = [
            entrega
            for entrega in entregas_qs
            if self._item_tem_algum_marcador(entrega, marcadores_ids)
        ]
        for processo in processos:
            chart_payload = {
                **_chart_compare_payload(processo),
                "badge": "Comparativo compacto",
            }
            processo.chart_payload = chart_payload
            processo.chart_payload_json = json.dumps(chart_payload)
        for entrega in entregas:
            chart_payload = {
                **_chart_compare_payload(entrega),
                "badge": "Comparativo compacto",
            }
            entrega.chart_payload = chart_payload
            entrega.chart_payload_json = json.dumps(chart_payload)

        content_type_indicador_estrategico = ContentType.objects.get_for_model(IndicadorEstrategico)
        content_type_indicador_tatico = ContentType.objects.get_for_model(IndicadorTatico)
        content_type_processo = ContentType.objects.get_for_model(Processo)
        content_type_entrega = ContentType.objects.get_for_model(Entrega)
        content_types_filtro = [
            content_type_indicador_estrategico,
            content_type_indicador_tatico,
            content_type_processo,
            content_type_entrega,
        ]
        marcadores_em_uso = Marcador.objects.filter(
            ativo=True,
        ).filter(
            Q(vinculos_itens__content_type__in=content_types_filtro)
            | Q(vinculos_automaticos_grupo_itens__content_type__in=content_types_filtro)
        ).distinct().order_by("nome")

        context["indicadores_page_obj"] = self._paginate(indicadores, "indicador_page")
        context["processo_page_obj"] = self._paginate(processos, "processo_page")
        context["entrega_page_obj"] = self._paginate(entregas, "entrega_page")

        context["qs_indicador"] = self._querystring_without("indicador_page")
        context["qs_processo"] = self._querystring_without("processo_page")
        context["qs_entrega"] = self._querystring_without("entrega_page")
        context["marcadores_filtro"] = list(marcadores_em_uso)
        context["marcadores_selecionados_ids"] = sorted(marcadores_ids)
        return context


@login_required
@require_GET
def painel_consolidado_grafico_variaveis_api(request):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `request`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not request.user.has_perm("sala_situacao.view_salasituacaopainel"):
        return JsonResponse({"detail": "Sem permissão."}, status=403)

    ids_param = (request.GET.get("variavel_ids") or "").strip()
    periodo = (request.GET.get("periodo") or "ano_atual").strip()
    ids = [int(item) for item in ids_param.split(",") if item.strip().isdigit()]
    if not ids:
        return JsonResponse({"labels": [], "series": [], "meta": {"periodo": periodo}})

    qs = IndicadorCicloValor.objects.select_related("ciclo", "variavel").filter(variavel_id__in=ids)
    hoje = timezone.localdate()
    if periodo == "ano_atual":
        inicio = hoje.replace(month=1, day=1)
        fim = hoje.replace(month=12, day=31)
        qs = qs.filter(ciclo__periodo_fim__gte=inicio, ciclo__periodo_fim__lte=fim)

    por_variavel_ciclo = defaultdict(list)
    for item in qs.order_by("variavel_id", "ciclo_id", "-atualizado_em", "-id"):
        por_variavel_ciclo[(item.variavel_id, item.ciclo_id)].append(item)

    ponto_por_variavel = defaultdict(dict)
    for (variavel_id, _), itens in por_variavel_ciclo.items():
        escolhido = itens[0]
        label_data = timezone.localtime(escolhido.atualizado_em).date().isoformat()
        ponto_por_variavel[variavel_id][label_data] = float(escolhido.valor)

    labels = sorted({data for pontos in ponto_por_variavel.values() for data in pontos.keys()})
    if not labels:
        return JsonResponse({"labels": [], "series": [], "meta": {"periodo": periodo}})

    cores = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#17becf",
        "#bcbd22",
        "#7f7f7f",
    ]
    variaveis = {item.id: item for item in IndicadorVariavel.objects.filter(id__in=ids)}
    series = []
    for idx, variavel_id in enumerate(ids):
        variavel = variaveis.get(variavel_id)
        if not variavel:
            continue
        pontos = ponto_por_variavel.get(variavel_id, {})
        series.append(
            {
                "variavel_id": variavel_id,
                "label": variavel.nome,
                "unidade": variavel.unidade_medida,
                "cor": cores[idx % len(cores)],
                "dados": [pontos.get(label) for label in labels],
            }
        )

    return JsonResponse({"labels": labels, "series": series, "meta": {"periodo": periodo}})


class IndicadoresTaticosPorIndicadorEstrategicoView(PermissionRequiredMixin, DetailView):
    """Classe `IndicadoresTaticosPorIndicadorEstrategicoView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    template_name = "sala_situacao/fluxo_indicadores_taticos.html"
    context_object_name = "indicador_estrategico"
    permission_required = "sala_situacao.view_indicadortatico"

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["indicadores_taticos"] = self.object.processos.all().order_by("nome")
        return context


class ProcessosPorIndicadorTaticoView(PermissionRequiredMixin, DetailView):
    """Classe `ProcessosPorIndicadorTaticoView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    template_name = "sala_situacao/fluxo_processos.html"
    context_object_name = "indicador_estrategico"
    permission_required = "sala_situacao.view_processo"

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["processos"] = _filtrar_processos_visiveis_para_usuario(
            self.object.processos.prefetch_related(
            "indicadores_estrategicos",
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
            ).order_by("nome"),
            self.request.user,
        )
        context["indicador_estrategico_retorno"] = self.object
        return context


class EntregasPorProcessoView(PermissionRequiredMixin, DetailView):
    """Classe `EntregasPorProcessoView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    template_name = "sala_situacao/fluxo_entregas.html"
    context_object_name = "processo"
    permission_required = "sala_situacao.view_entrega"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_entrega")
            or user.has_perm("sala_situacao.change_entrega")
            or user.has_perm("sala_situacao.monitorar_entrega")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        entregas_qs = self.object.entregas.all()
        if not (
            self.request.user.has_perm("sala_situacao.view_entrega")
            or self.request.user.has_perm("sala_situacao.change_entrega")
            or _usuario_admin_sala(self.request.user)
        ):
            entregas_qs = entregas_qs.filter(
                variavel_monitoramento__grupos_monitoramento__in=self.request.user.groups.all()
            ).distinct()
        context["entregas"] = ordenar_entregas_por_ciclo(
            entregas_qs.prefetch_related(
                "marcadores_vinculos__marcador",
                "processos__marcadores_vinculos__marcador",
            )
        )
        context["indicador_estrategico_retorno"] = self.object.indicadores_estrategicos.order_by("nome").first()
        return context


class BaseFormContextMixin:
    """Classe `BaseFormContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    template_name = "sala_situacao/form.html"
    delete_url_name = None

    def _build_assistencia_evolucao(self, instance):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not instance:
            return "Sem filhos vinculados, a evolução pode ser preenchida manualmente."
        if getattr(instance, "eh_indicador_matematico", False):
            return (
                "Indicador matemático: evolução calculada por fórmula e valores de monitoramento. "
                "A evolução manual não é utilizada."
            )
        if instance.tem_filhos_relacionados:
            return (
                "Este item possui filhos vinculados. A evolução é calculada automaticamente "
                "com base no progresso dos itens relacionados."
            )
        return "Este item não possui filhos vinculados. A evolução manual pode ser atualizada."

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["titulo"] = self.titulo
        context["cancel_url"] = self.cancel_url
        model_class = getattr(self, "model", None)
        model_name = getattr(getattr(model_class, "_meta", None), "model_name", "")
        tipo_map = {
            "indicadorestrategico": "ie",
            "indicadortatico": "it",
            "processo": "processo",
            "entrega": "entrega",
        }
        context["marcador_item_tipo"] = tipo_map.get(model_name, "")
        context["marcador_sugestoes_url"] = reverse("sala_marcador_sugestoes_api")
        context["marcador_criar_url"] = reverse("sala_marcador_criar_api")
        context["marcador_cor_url_template"] = reverse("sala_marcador_cor_api", kwargs={"pk": 0})
        context["marcador_excluir_url_template"] = reverse("sala_marcador_excluir_api", kwargs={"pk": 0})
        context["marcador_item_url_template"] = reverse(
            "sala_item_marcadores_api",
            kwargs={"tipo": "__tipo__", "pk": 0},
        )
        context["assistencia_evolucao"] = self._build_assistencia_evolucao(
            getattr(self, "object", None)
        )
        obj = getattr(self, "object", None)
        context["marcador_item_id"] = obj.pk if obj and getattr(obj, "pk", None) else ""
        context["variavel_sugestoes_url"] = reverse("sala_variavel_sugestoes_api")
        form = context.get("form")
        if model_name == "entrega" and form is not None:
            ordered_field_names = [
                "nome",
                "descricao",
                "processos",
                "marcadores_ids",
                "data_entrega_estipulada",
                "evolucao_manual",
                "valor_monitoramento",
            ]
            context["ordered_form_fields"] = [
                form[name] for name in ordered_field_names if name in form.fields
            ]
        context["monitoramento_grupos"] = [
            {"id": grupo.id, "nome": grupo.name}
            for grupo in Group.objects.order_by("name")
        ]
        if obj and getattr(obj, "pk", None) and self.delete_url_name:
            context["delete_url"] = reverse(self.delete_url_name, kwargs={"pk": obj.pk})
            model_meta = obj._meta
            if isinstance(obj, (IndicadorEstrategico, IndicadorTatico)):
                context["can_delete"] = _user_can_delete_indicator(self.request.user, obj)
            elif isinstance(obj, Processo):
                context["can_delete"] = (
                    self.request.user.has_perm("sala_situacao.delete_processo")
                    and (
                        _usuario_admin_sala(self.request.user)
                        or not obj.origem_automatica_monitoramento
                    )
                )
            else:
                delete_perm = f"{model_meta.app_label}.delete_{model_meta.model_name}"
                context["can_delete"] = self.request.user.has_perm(delete_perm)
        return context


class BaseStatusMessageMixin:
    """Classe `BaseStatusMessageMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    entidade_label = "Item"

    def _is_update_view(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return isinstance(self, UpdateView)

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        is_update = self._is_update_view()
        response = super().form_valid(form)
        if getattr(self.object, "eh_indicador_matematico", False):
            if hasattr(self.object, "sincronizar_variaveis_da_formula"):
                self.object.sincronizar_variaveis_da_formula()
            if hasattr(self.object, "gerar_ciclos_monitoramento"):
                self.object.gerar_ciclos_monitoramento()
            if hasattr(self.object, "sincronizar_estrutura_processual_monitoramento"):
                self.object.sincronizar_estrutura_processual_monitoramento()

        acao = "atualizado" if is_update else "criado"
        messages.success(
            self.request,
            f"{self.entidade_label} {acao} com sucesso.",
        )

        if getattr(self.object, "eh_indicador_matematico", False):
            messages.info(
                self.request,
                "Indicador matemático salvo. Variáveis da fórmula e trilha processual de monitoramento foram sincronizadas automaticamente.",
            )
        elif self.object.tem_filhos_relacionados:
            messages.info(
                self.request,
                "Evolução calculada automaticamente pelos itens vinculados.",
            )
            if is_update:
                messages.info(
                    self.request,
                    "Este ajuste pode refletir automaticamente nos níveis superiores.",
                )
        elif "evolucao_manual" in form.changed_data:
            messages.info(
                self.request,
                "Evolução manual atualizada para este item sem filhos vinculados.",
            )
        return response


class AuditHistoryContextMixin:
    """Classe `AuditHistoryContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    audit_limit = 15

    def _get_audit_logs(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        content_type = ContentType.objects.get_for_model(self.object.__class__)
        return (
            AuditLog.objects.select_related("user")
            .filter(content_type=content_type, object_id=str(self.object.pk))
            .order_by("-timestamp")[: self.audit_limit]
        )

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        logs = list(self._get_audit_logs())
        context["historico_alteracoes"] = logs
        context["ultima_alteracao_usuario"] = next(
            (log.user for log in logs if log.user),
            None,
        )
        return context


class ItemNotesContextMixin:
    """Classe `ItemNotesContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    nota_form_class = NotaItemForm
    notas_limit = 30

    def _get_notas(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        content_type = ContentType.objects.get_for_model(self.object.__class__)
        return (
            NotaItem.objects.select_related("criado_por")
            .filter(content_type=content_type, object_id=self.object.pk)
            .order_by("-criado_em")[: self.notas_limit]
        )

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["nota_form"] = kwargs.get("nota_form") or self.nota_form_class()
        context["notas_item"] = list(self._get_notas())
        return context

    def post(self, request, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        nota_form = self.nota_form_class(request.POST)
        if nota_form.is_valid():
            content_type = ContentType.objects.get_for_model(self.object.__class__)
            NotaItem.objects.create(
                content_type=content_type,
                object_id=self.object.pk,
                texto=nota_form.cleaned_data["texto"].strip(),
                criado_por=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, "Nota adicionada com sucesso.")
            return HttpResponseRedirect(request.path)

        messages.error(request, "Não foi possível salvar a nota. Verifique o conteúdo informado.")
        context = self.get_context_data(nota_form=nota_form)
        return self.render_to_response(context)


class RelatedHierarchyContextMixin:
    """Classe `RelatedHierarchyContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def get_related_groups(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return []

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["related_groups"] = self.get_related_groups()
        return context


class IndicadorMonitoramentoContextMixin:
    """Classe `IndicadorMonitoramentoContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    @staticmethod
    def _status_ciclo_monitoramento(ciclo):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `ciclo`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        preenchido = any(
            entrega.valor_monitoramento is not None
            for entrega in ciclo.entregas_monitoramento.all()
        )
        if preenchido:
            return "Concluido", "monitoramento-status--verde"
        return "Pendente", "monitoramento-status--vermelho"

    def _build_monitoramento_contexto(self, indicador):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not getattr(indicador, "eh_indicador_matematico", False):
            return {}
        content_type = ContentType.objects.get_for_model(indicador.__class__)
        variaveis = list(
            IndicadorVariavel.objects.filter(
            content_type=content_type,
            object_id=indicador.pk,
        ).order_by("ordem", "nome")
        )
        variaveis_monitoramento = []
        variaveis_concluidas = 0
        ultima_atualizacao = None
        for variavel in variaveis:
            ciclos = list(
                IndicadorVariavelCicloMonitoramento.objects.filter(variavel=variavel)
                .prefetch_related("entregas_monitoramento")
                .order_by("periodo_inicio", "numero")
            )
            possui_conclusao = False
            for ciclo in ciclos:
                status_texto, status_classe = self._status_ciclo_monitoramento(ciclo)
                ciclo.monitoramento_status_texto = status_texto
                ciclo.monitoramento_status_classe = status_classe
                valor_monitorado = None
                entregas_preenchidas = [
                    entrega
                    for entrega in ciclo.entregas_monitoramento.all()
                    if entrega.valor_monitoramento is not None
                ]
                if entregas_preenchidas:
                    entrega_referencia = max(
                        entregas_preenchidas,
                        key=lambda entrega: (
                            entrega.atualizado_em or timezone.now(),
                            entrega.pk or 0,
                        ),
                    )
                    valor_monitorado = entrega_referencia.valor_monitoramento
                ciclo.monitoramento_valor = valor_monitorado
                if status_texto == "Concluido":
                    possui_conclusao = True
                    if not ultima_atualizacao or ciclo.atualizado_em > ultima_atualizacao:
                        ultima_atualizacao = ciclo.atualizado_em
            if possui_conclusao:
                variaveis_concluidas += 1
            variaveis_monitoramento.append(
                {
                    "variavel": variavel,
                    "ciclos": ciclos,
                }
            )
        total_variaveis = len(variaveis)
        resumo_percentual = round((variaveis_concluidas / total_variaveis) * 100, 2) if total_variaveis else 0
        return {
            "indicador_variaveis": variaveis,
            "variaveis_monitoramento": variaveis_monitoramento,
            "monitoramento_resumo": {
                "percentual_variaveis_concluidas": resumo_percentual,
                "ultima_atualizacao": ultima_atualizacao,
            },
        }

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context.update(self._build_monitoramento_contexto(self.object))
        return context


class BaseDeleteContextMixin:
    """Classe `BaseDeleteContextMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    template_name = "sala_situacao/confirm_delete.html"
    success_url = None
    voltar_url_name = None
    titulo = ""
    mensagem = ""

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["titulo"] = self.titulo
        context["mensagem"] = self.mensagem
        context["voltar_url"] = reverse(self.voltar_url_name, kwargs={"pk": self.object.pk})
        return context

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        messages.success(self.request, f"{self.object} excluído com sucesso.")
        return super().form_valid(form)


class IndicadorEstrategicoListView(PermissionRequiredMixin, ListView):
    """Classe `IndicadorEstrategicoListView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    context_object_name = "indicadores"
    template_name = "sala_situacao/indicador_estrategico_list.html"
    permission_required = "sala_situacao.view_indicadorestrategico"

    def has_permission(self):
        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_indicadorestrategico")
            or user.has_perm("sala_situacao.change_indicadorestrategico")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        indicadores_permitidos = _indicadores_estrategicos_queryset_para_usuario(self.request.user).values_list(
            "id", flat=True
        )
        return IndicadorEstrategico.objects.prefetch_related(
            "marcadores_vinculos__marcador",
        ).filter(id__in=indicadores_permitidos).order_by("nome")


class IndicadorEstrategicoDetailView(
    PermissionRequiredMixin,
    ItemNotesContextMixin,
    AuditHistoryContextMixin,
    IndicadorMonitoramentoContextMixin,
    RelatedHierarchyContextMixin,
    DetailView,
):
    """Classe `IndicadorEstrategicoDetailView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    context_object_name = "indicador"
    template_name = "sala_situacao/indicador_estrategico_detail.html"
    permission_required = "sala_situacao.view_indicadorestrategico"

    def has_permission(self):
        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_indicadorestrategico")
            or user.has_perm("sala_situacao.change_indicadorestrategico")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        indicadores_permitidos = _indicadores_estrategicos_queryset_para_usuario(self.request.user).values_list(
            "id", flat=True
        )
        return IndicadorEstrategico.objects.prefetch_related(
            "marcadores_vinculos__marcador",
        ).filter(id__in=indicadores_permitidos)

    def get_related_groups(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        content_type_ie = ContentType.objects.get_for_model(IndicadorEstrategico)
        indicadores_taticos = IndicadorEstrategico.objects.filter(pk=self.object.pk)
        processos_via_it = Processo.objects.filter(indicadores_estrategicos=self.object).distinct()
        processos_monitoramento = Processo.objects.filter(
            entregas__variavel_monitoramento__content_type=content_type_ie,
            entregas__variavel_monitoramento__object_id=self.object.pk,
        ).distinct()
        processos = _filtrar_processos_visiveis_para_usuario(
            (processos_via_it | processos_monitoramento).distinct().order_by("nome"),
            self.request.user,
        )

        entregas_via_it = Entrega.objects.filter(processos__indicadores_estrategicos=self.object).distinct()
        entregas_monitoramento = Entrega.objects.filter(
            variavel_monitoramento__content_type=content_type_ie,
            variavel_monitoramento__object_id=self.object.pk,
        ).distinct()
        entregas = (entregas_via_it | entregas_monitoramento).distinct()
        entregas = ordenar_entregas_por_ciclo(entregas)
        return [
            {
                "titulo": "Indicadores relacionados",
                "itens": indicadores_taticos,
                "url_name": "sala_indicador_estrategico_detail",
                "vazio": "Nenhum indicador relacionado.",
            },
            {
                "titulo": "Processos relacionados",
                "itens": processos,
                "url_name": "sala_processo_detail",
                "vazio": "Nenhum processo relacionado.",
            },
            {
                "titulo": "Entregas relacionadas",
                "itens": entregas,
                "url_name": "sala_entrega_detail",
                "vazio": "Nenhuma entrega relacionada.",
            },
        ]

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["can_edit"] = _user_can_update_indicator(self.request.user, self.object)
        context["can_delete"] = _user_can_delete_indicator(self.request.user, self.object)
        return context


class IndicadorEstrategicoCreateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, CreateView
):
    """Classe `IndicadorEstrategicoCreateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    form_class = IndicadorEstrategicoForm
    permission_required = "sala_situacao.add_indicadorestrategico"
    entidade_label = "Indicador"
    titulo = "Novo indicador"
    cancel_url = reverse_lazy("sala_indicador_estrategico_list")

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not form.instance.criado_por_id:
            form.instance.criado_por = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.object.pk})


class IndicadorOwnerPermissionMixin(PermissionRequiredMixin):
    """Classe `IndicadorOwnerPermissionMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    owner_check_kind = "change"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        if self.owner_check_kind == "delete":
            return _user_can_delete_indicator(self.request.user, self.object)
        return _user_can_update_indicator(self.request.user, self.object)


class IndicadorEstrategicoUpdateView(
    IndicadorOwnerPermissionMixin, BaseStatusMessageMixin, BaseFormContextMixin, UpdateView
):
    """Classe `IndicadorEstrategicoUpdateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    form_class = IndicadorEstrategicoForm
    permission_required = "sala_situacao.change_indicadorestrategico"
    entidade_label = "Indicador"
    titulo = "Editar indicador"
    cancel_url = reverse_lazy("sala_indicador_estrategico_list")
    delete_url_name = "sala_indicador_estrategico_delete"

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.object.pk})


class IndicadorEstrategicoDeleteView(PermissionRequiredMixin, BaseDeleteContextMixin, DeleteView):
    """Classe `IndicadorEstrategicoDeleteView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorEstrategico
    permission_required = "sala_situacao.delete_indicadorestrategico"
    success_url = reverse_lazy("sala_indicador_estrategico_list")
    voltar_url_name = "sala_indicador_estrategico_detail"
    titulo = "Excluir indicador"
    mensagem = "Tem certeza que deseja excluir este indicador?"
    owner_check_kind = "delete"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        return _user_can_delete_indicator(self.request.user, self.object)

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        cascata = _resolver_cascata_ie(self.object)
        entregas_ids = list(cascata["entregas"].values_list("id", flat=True))
        processos_ids = list(cascata["processos"].values_list("id", flat=True))
        indicadores_taticos_ids = list(cascata["indicadores_taticos"].values_list("id", flat=True))
        with transaction.atomic():
            Entrega.objects.filter(id__in=entregas_ids).delete()
            Processo.objects.filter(id__in=processos_ids).delete()
            _limpar_recursos_genericos_do_indicador(
                IndicadorTatico,
                indicadores_taticos_ids,
            )
            IndicadorTatico.objects.filter(id__in=indicadores_taticos_ids).delete()
            _limpar_recursos_genericos_do_indicador(IndicadorEstrategico, [self.object.pk])
            self.object.delete()
        messages.success(
            self.request,
            "Indicador e cadeia exclusiva relacionada excluídos com sucesso.",
        )
        return HttpResponseRedirect(self.get_success_url())


class IndicadorTaticoListView(PermissionRequiredMixin, ListView):
    """Classe `IndicadorTaticoListView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorTatico
    context_object_name = "indicadores"
    template_name = "sala_situacao/indicador_tatico_list.html"
    permission_required = "sala_situacao.view_indicadortatico"

    def has_permission(self):
        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_indicadortatico")
            or user.has_perm("sala_situacao.change_indicadortatico")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        indicadores_permitidos = _indicadores_taticos_queryset_para_usuario(self.request.user).values_list(
            "id", flat=True
        )
        return IndicadorTatico.objects.prefetch_related(
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
        ).filter(id__in=indicadores_permitidos).order_by("nome")


class IndicadorTaticoDetailView(
    PermissionRequiredMixin,
    ItemNotesContextMixin,
    AuditHistoryContextMixin,
    IndicadorMonitoramentoContextMixin,
    RelatedHierarchyContextMixin,
    DetailView,
):
    """Classe `IndicadorTaticoDetailView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorTatico
    context_object_name = "indicador"
    template_name = "sala_situacao/indicador_tatico_detail.html"
    permission_required = "sala_situacao.view_indicadortatico"

    def has_permission(self):
        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_indicadortatico")
            or user.has_perm("sala_situacao.change_indicadortatico")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        indicadores_permitidos = _indicadores_taticos_queryset_para_usuario(self.request.user).values_list(
            "id", flat=True
        )
        return IndicadorTatico.objects.prefetch_related(
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
        ).filter(id__in=indicadores_permitidos)

    def get_related_groups(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        processos = _filtrar_processos_visiveis_para_usuario(
            self.object.processos.all().order_by("nome"),
            self.request.user,
        )
        entregas = (
            Entrega.objects.filter(processos__indicadores_taticos=self.object)
            .distinct()
        )
        entregas = ordenar_entregas_por_ciclo(entregas)
        return [
            {
                "titulo": "Processos relacionados",
                "itens": processos,
                "url_name": "sala_processo_detail",
                "vazio": "Nenhum processo relacionado.",
            },
            {
                "titulo": "Entregas relacionadas",
                "itens": entregas,
                "url_name": "sala_entrega_detail",
                "vazio": "Nenhuma entrega relacionada.",
            },
        ]

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["can_edit"] = _user_can_update_indicator(self.request.user, self.object)
        context["can_delete"] = _user_can_delete_indicator(self.request.user, self.object)
        return context


class IndicadorTaticoCreateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, CreateView
):
    """Classe `IndicadorTaticoCreateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorTatico
    form_class = IndicadorTaticoForm
    permission_required = "sala_situacao.add_indicadortatico"
    entidade_label = "Indicador"
    titulo = "Novo indicador"
    cancel_url = reverse_lazy("sala_indicador_tatico_list")

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not form.instance.criado_por_id:
            form.instance.criado_por = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_indicador_tatico_detail", kwargs={"pk": self.object.pk})


class IndicadorTaticoUpdateView(
    IndicadorOwnerPermissionMixin, BaseStatusMessageMixin, BaseFormContextMixin, UpdateView
):
    """Classe `IndicadorTaticoUpdateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorTatico
    form_class = IndicadorTaticoForm
    permission_required = "sala_situacao.change_indicadortatico"
    entidade_label = "Indicador"
    titulo = "Editar indicador"
    cancel_url = reverse_lazy("sala_indicador_tatico_list")
    delete_url_name = "sala_indicador_tatico_delete"

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_indicador_tatico_detail", kwargs={"pk": self.object.pk})


class IndicadorTaticoDeleteView(PermissionRequiredMixin, BaseDeleteContextMixin, DeleteView):
    """Classe `IndicadorTaticoDeleteView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorTatico
    permission_required = "sala_situacao.delete_indicadortatico"
    success_url = reverse_lazy("sala_indicador_tatico_list")
    voltar_url_name = "sala_indicador_tatico_detail"
    titulo = "Excluir indicador"
    mensagem = "Tem certeza que deseja excluir este indicador?"
    owner_check_kind = "delete"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        return _user_can_delete_indicator(self.request.user, self.object)

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        cascata = _resolver_cascata_it(self.object)
        with transaction.atomic():
            cascata["entregas"].delete()
            cascata["processos"].delete()
            _limpar_recursos_genericos_do_indicador(IndicadorTatico, [self.object.pk])
            self.object.delete()
        messages.success(
            self.request,
            "Indicador e cadeia exclusiva relacionada excluídos com sucesso.",
        )
        return HttpResponseRedirect(self.get_success_url())


class IndicadorOperacaoMixin(PermissionRequiredMixin):
    """Classe `IndicadorOperacaoMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    indicador_kind_map = {
        "estrategico": {
            "model": IndicadorEstrategico,
            "detail_url_name": "sala_indicador_estrategico_detail",
            "label": "Indicador",
        },
        "tatico": {
            "model": IndicadorTatico,
            "detail_url_name": "sala_indicador_tatico_detail",
            "label": "Indicador",
        },
    }

    def get_kind_config(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        kind = self.kwargs.get("tipo")
        config = self.indicador_kind_map.get(kind)
        if not config:
            raise Http404("Tipo de indicador inválido.")
        return config

    def get_indicador(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        config = self.get_kind_config()
        indicador = config["model"].objects.filter(pk=self.kwargs["pk"]).first()
        if not indicador:
            raise Http404("Indicador não encontrado.")
        return indicador

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        config = self.get_kind_config()
        return reverse(config["detail_url_name"], kwargs={"pk": self.indicador.pk})

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.indicador = self.get_indicador()
        meta = self.indicador._meta
        return self.request.user.has_perm(f"{meta.app_label}.change_{meta.model_name}")


class IndicadorVariavelCreateView(IndicadorOperacaoMixin, CreateView):
    """Classe `IndicadorVariavelCreateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = IndicadorVariavel
    form_class = IndicadorVariavelForm
    template_name = "sala_situacao/indicador_variavel_form.html"

    def dispatch(self, request, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.indicador = self.get_indicador()
        messages.error(
            request,
            "Não é permitido lançar novas variáveis após a criação do indicador. "
            "As variáveis são definidas na criação do indicador.",
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        config = self.get_kind_config()
        context["indicador"] = self.indicador
        context["titulo"] = f"Nova variável - {self.indicador.nome}"
        context["cancel_url"] = reverse(config["detail_url_name"], kwargs={"pk": self.indicador.pk})
        return context

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        content_type = ContentType.objects.get_for_model(self.indicador.__class__)
        form.instance.content_type = content_type
        form.instance.object_id = self.indicador.pk
        response = super().form_valid(form)
        messages.success(self.request, "Variável cadastrada com sucesso.")
        return response


class ProcessoListView(PermissionRequiredMixin, ListView):
    """Classe `ProcessoListView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    context_object_name = "processos"
    template_name = "sala_situacao/processo_list.html"
    permission_required = "sala_situacao.view_processo"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_processo")
            or user.has_perm("sala_situacao.change_processo")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        queryset = Processo.objects.prefetch_related(
            "indicadores_estrategicos",
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
        ).order_by("nome")
        processos_permitidos = _processos_queryset_para_usuario(self.request.user).values_list("id", flat=True)
        queryset = queryset.filter(id__in=processos_permitidos).distinct()

        setor_raw = (self.request.GET.get("setor") or "").strip()
        setores_visiveis = _setores_visiveis_para_usuario(self.request.user)
        setor_ids_visiveis = set(setores_visiveis.values_list("id", flat=True))
        if setor_raw.isdigit():
            setor_id = int(setor_raw)
            if setor_id in setor_ids_visiveis:
                queryset = _filtrar_queryset_por_setor(queryset, Processo, setor_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["setores_disponiveis"] = list(_setores_visiveis_para_usuario(self.request.user))
        context["setor_selecionado_id"] = (self.request.GET.get("setor") or "").strip()
        return context


class ProcessoDetailView(
    PermissionRequiredMixin,
    ItemNotesContextMixin,
    AuditHistoryContextMixin,
    RelatedHierarchyContextMixin,
    DetailView,
):
    """Classe `ProcessoDetailView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    context_object_name = "processo"
    template_name = "sala_situacao/processo_detail.html"
    permission_required = "sala_situacao.view_processo"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_processo")
            or user.has_perm("sala_situacao.change_processo")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        queryset = Processo.objects.prefetch_related(
            "indicadores_estrategicos",
            "marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
            "indicadores_estrategicos__marcadores_vinculos__marcador",
            "entregas__marcadores_vinculos__marcador",
        )
        processos_permitidos = _processos_queryset_para_usuario(self.request.user).values_list("id", flat=True)
        return queryset.filter(id__in=processos_permitidos).distinct()

    def get_related_groups(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return [
            {
                "titulo": "Entregas relacionadas",
                "itens": ordenar_entregas_por_ciclo(self.object.entregas.all()),
                "url_name": "sala_entrega_detail",
                "vazio": "Nenhuma entrega relacionada.",
            }
        ]

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        pode_editar = self.request.user.has_perm("sala_situacao.change_processo") and (
            _usuario_admin_sala(self.request.user) or not self.object.origem_automatica_monitoramento
        )
        pode_excluir = self.request.user.has_perm("sala_situacao.delete_processo") and (
            _usuario_admin_sala(self.request.user) or not self.object.origem_automatica_monitoramento
        )
        context["can_edit"] = pode_editar
        context["can_delete"] = pode_excluir
        return context


class ProcessoCreateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, CreateView
):
    """Classe `ProcessoCreateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    form_class = ProcessoForm
    permission_required = "sala_situacao.add_processo"
    entidade_label = "Processo"
    titulo = "Novo processo"
    cancel_url = reverse_lazy("sala_processo_list")

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_processo_detail", kwargs={"pk": self.object.pk})


class ProcessoUpdateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, UpdateView
):
    """Classe `ProcessoUpdateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    form_class = ProcessoForm
    permission_required = "sala_situacao.change_processo"
    entidade_label = "Processo"
    titulo = "Editar processo"
    cancel_url = reverse_lazy("sala_processo_list")
    delete_url_name = "sala_processo_delete"

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_processo_detail", kwargs={"pk": self.object.pk})

    def dispatch(self, request, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        if self.object.origem_automatica_monitoramento and not _usuario_admin_sala(request.user):
            raise PermissionDenied("Processos automáticos de monitoramento não podem ser editados manualmente.")
        return super().dispatch(request, *args, **kwargs)


class ProcessoDeleteView(PermissionRequiredMixin, BaseDeleteContextMixin, DeleteView):
    """Classe `ProcessoDeleteView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Processo
    permission_required = "sala_situacao.delete_processo"
    success_url = reverse_lazy("sala_processo_list")
    voltar_url_name = "sala_processo_detail"
    titulo = "Excluir processo"
    mensagem = "Tem certeza que deseja excluir este processo?"

    def dispatch(self, request, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.object = self.get_object()
        if self.object.origem_automatica_monitoramento and not _usuario_admin_sala(request.user):
            raise PermissionDenied("Processos automáticos de monitoramento não podem ser excluídos manualmente.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        entregas_relacionadas = self.object.entregas.all().distinct()
        total_entregas = entregas_relacionadas.count()
        if total_entregas:
            entregas_relacionadas.delete()
            messages.info(
                self.request,
                f"{total_entregas} entrega(s) relacionada(s) também foi(ram) excluída(s).",
            )
        return super().form_valid(form)


class EntregaListView(PermissionRequiredMixin, ListView):
    """Classe `EntregaListView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Entrega
    context_object_name = "entregas"
    template_name = "sala_situacao/entrega_list.html"
    permission_required = "sala_situacao.view_entrega"
    paginate_by = 10

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_entrega")
            or user.has_perm("sala_situacao.change_entrega")
            or user.has_perm("sala_situacao.monitorar_entrega")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        queryset = (
            _entregas_queryset_para_usuario(self.request.user)
            .select_related("ciclo_monitoramento", "variavel_monitoramento")
            .prefetch_related(
                "marcadores_vinculos__marcador",
                "processos__marcadores_vinculos__marcador",
                "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
                "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
            )
            .annotate(
                ciclo_ordenacao=Coalesce(
                    "ciclo_monitoramento__numero",
                    Value(999999),
                    output_field=IntegerField(),
                ),
                entregue_ordenacao=Case(
                    When(evolucao_manual__gte=100, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .order_by("entregue_ordenacao", "ciclo_ordenacao", "nome")
        )
        setor_raw = (self.request.GET.get("setor") or "").strip()
        setores_visiveis = _setores_visiveis_para_usuario(self.request.user)
        setor_ids_visiveis = set(setores_visiveis.values_list("id", flat=True))
        if setor_raw.isdigit():
            setor_id = int(setor_raw)
            if setor_id in setor_ids_visiveis:
                queryset = _filtrar_queryset_por_setor(queryset, Entrega, setor_id)
        return queryset

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        context["setores_disponiveis"] = list(_setores_visiveis_para_usuario(self.request.user))
        context["setor_selecionado_id"] = (self.request.GET.get("setor") or "").strip()
        context["entregas_calendario_api_url"] = _reverse_sala_route(
            self.request, "sala_entrega_calendario_api"
        )
        return context


@login_required
@require_GET
def entrega_calendario_api(request):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `request`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not (
        request.user.has_perm("sala_situacao.view_entrega")
        or request.user.has_perm("sala_situacao.change_entrega")
        or request.user.has_perm("sala_situacao.monitorar_entrega")
        or user_is_monitoring_group_member(request.user)
        or _usuario_admin_sala(request.user)
    ):
        return JsonResponse({"detail": "Sem permissão."}, status=403)

    hoje = timezone.localdate()
    ano_raw = (request.GET.get("ano") or "").strip()
    mes_raw = (request.GET.get("mes") or "").strip()
    ano = int(ano_raw) if ano_raw.isdigit() else hoje.year
    mes = int(mes_raw) if mes_raw.isdigit() else hoje.month
    if mes < 1 or mes > 12:
        return JsonResponse({"detail": "Mês inválido."}, status=400)

    inicio = hoje.replace(year=ano, month=mes, day=1)
    if mes == 12:
        proximo_mes = inicio.replace(year=ano + 1, month=1, day=1)
    else:
        proximo_mes = inicio.replace(month=mes + 1, day=1)
    fim = proximo_mes - timedelta(days=1)

    entregas = (
        _entregas_queryset_para_usuario(request.user)
        .filter(data_entrega_estipulada__gte=inicio, data_entrega_estipulada__lte=fim)
        .select_related("ciclo_monitoramento", "variavel_monitoramento")
        .order_by("data_entrega_estipulada", "nome")
    )
    setor_raw = (request.GET.get("setor") or "").strip()
    setores_visiveis = _setores_visiveis_para_usuario(request.user)
    setor_ids_visiveis = set(setores_visiveis.values_list("id", flat=True))
    if setor_raw.isdigit():
        setor_id = int(setor_raw)
        if setor_id in setor_ids_visiveis:
            entregas = _filtrar_queryset_por_setor(entregas, Entrega, setor_id)
    resultados = []
    for entrega in entregas:
        entregue = entrega.progresso_percentual >= 100
        resultados.append(
            {
                "id": entrega.pk,
                "data": entrega.data_entrega_estipulada.isoformat(),
                "periodo_inicio": entrega.periodo_inicio.isoformat() if entrega.periodo_inicio else None,
                "periodo_fim": entrega.periodo_fim.isoformat() if entrega.periodo_fim else None,
                "nome": entrega.nome,
                "descricao": (entrega.descricao or "").strip() or "Sem descrição.",
                "entregue": entregue,
                "status_label": "Entregue" if entregue else "Não entregue",
                "url": reverse("sala_entrega_detail", kwargs={"pk": entrega.pk}),
            }
        )

    return JsonResponse(
        {
            "ano": ano,
            "mes": mes,
            "results": resultados,
        }
    )


class EntregaDetailView(
    PermissionRequiredMixin,
    ItemNotesContextMixin,
    AuditHistoryContextMixin,
    RelatedHierarchyContextMixin,
    DetailView,
):
    """Classe `EntregaDetailView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Entrega
    context_object_name = "entrega"
    template_name = "sala_situacao/entrega_detail.html"
    permission_required = "sala_situacao.view_entrega"

    def has_permission(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        user = self.request.user
        return bool(
            user.has_perm("sala_situacao.view_entrega")
            or user.has_perm("sala_situacao.change_entrega")
            or user.has_perm("sala_situacao.monitorar_entrega")
            or user_is_monitoring_group_member(user)
            or _usuario_admin_sala(user)
        )

    def get_queryset(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return _entregas_queryset_para_usuario(self.request.user).prefetch_related(
            "marcadores_vinculos__marcador",
            "processos__marcadores_vinculos__marcador",
            "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
            "processos__indicadores_estrategicos__marcadores_vinculos__marcador",
        )

    def get_related_groups(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return [
            {
                "titulo": "Processos relacionados",
                "itens": _filtrar_processos_visiveis_para_usuario(
                    self.object.processos.all().order_by("nome"),
                    self.request.user,
                ),
                "url_name": "sala_processo_detail",
                "vazio": "Nenhum processo relacionado.",
            }
        ]

    def get_context_data(self, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        context = super().get_context_data(**kwargs)
        pode_monitorar = _user_can_monitorar_entrega(self.request.user, self.object)
        context["processos_visiveis"] = _filtrar_processos_visiveis_para_usuario(
            self.object.processos.all().order_by("nome"),
            self.request.user,
        )
        context["pode_monitorar"] = pode_monitorar
        context["can_edit"] = (
            self.request.user.has_perm("sala_situacao.change_entrega")
            and not (
                self.object.eh_entrega_monitoramento
                and self.object.variavel_monitoramento_id
                and self.request.user.has_perm("sala_situacao.monitorar_entrega")
                and not _usuario_admin_sala(self.request.user)
            )
        )
        context["can_delete"] = (
            self.request.user.has_perm("sala_situacao.delete_entrega")
            and not (
                self.object.eh_entrega_monitoramento
                and self.object.variavel_monitoramento_id
                and self.request.user.has_perm("sala_situacao.monitorar_entrega")
                and not _usuario_admin_sala(self.request.user)
            )
        )
        if self.object.eh_entrega_monitoramento and pode_monitorar:
            context["monitoramento_form"] = MonitoramentoEntregaForm(
                instance=self.object,
                usuario=self.request.user,
            )
        return context


@login_required
@require_POST
def entrega_monitorar(request, pk):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    entrega = Entrega.objects.filter(pk=pk).select_related("ciclo_monitoramento", "variavel_monitoramento").first()
    if not entrega:
        raise Http404("Entrega não encontrada.")
    if not _user_can_monitorar_entrega(request.user, entrega):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    if not entrega.eh_entrega_monitoramento:
        messages.error(request, "Esta entrega não é de monitoramento.")
        return HttpResponseRedirect(reverse("sala_entrega_detail", kwargs={"pk": pk}))
    form = MonitoramentoEntregaForm(
        request.POST,
        request.FILES,
        instance=entrega,
        usuario=request.user,
    )
    if form.is_valid():
        form.save()
        messages.success(request, "Monitoramento registrado com sucesso.")
    else:
        erros = []
        for campo_erros in form.errors.values():
            erros.extend(campo_erros)
        messages.error(request, "Não foi possível registrar o monitoramento: " + " ".join(str(e) for e in erros))
    return HttpResponseRedirect(reverse("sala_entrega_detail", kwargs={"pk": pk}))


class EntregaCreateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, CreateView
):
    """Classe `EntregaCreateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Entrega
    form_class = EntregaForm
    permission_required = "sala_situacao.add_entrega"
    entidade_label = "Entrega"
    titulo = "Nova entrega"
    cancel_url = reverse_lazy("sala_entrega_list")

    def get_form_kwargs(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_entrega_detail", kwargs={"pk": self.object.pk})


class EntregaUpdateView(
    PermissionRequiredMixin, BaseStatusMessageMixin, BaseFormContextMixin, UpdateView
):
    """Classe `EntregaUpdateView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Entrega
    form_class = EntregaForm
    permission_required = "sala_situacao.change_entrega"
    entidade_label = "Entrega"
    titulo = "Editar entrega"
    cancel_url = reverse_lazy("sala_entrega_list")
    delete_url_name = "sala_entrega_delete"

    def get_form_kwargs(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_success_url(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        return reverse("sala_entrega_detail", kwargs={"pk": self.object.pk})


class EntregaDeleteView(PermissionRequiredMixin, BaseDeleteContextMixin, DeleteView):
    """Classe `EntregaDeleteView` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    model = Entrega
    permission_required = "sala_situacao.delete_entrega"
    success_url = reverse_lazy("sala_entrega_list")
    voltar_url_name = "sala_entrega_detail"
    titulo = "Excluir entrega"
    mensagem = "Tem certeza que deseja excluir esta entrega?"
