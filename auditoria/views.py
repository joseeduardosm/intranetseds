"""
Views do app `auditoria`.

Este modulo expõe a interface HTTP de consulta dos logs auditados, com
controle de acesso administrativo, filtros por período, busca textual e
ordenação dinâmica.
Integra-se diretamente ao model `AuditLog` via ORM e renderiza template
de listagem para investigação operacional.
"""

from datetime import timedelta

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import models
from django.db.models.functions import Cast
from django.utils import timezone
from django.views.generic import ListView

from .models import AuditLog


class AuditLogListView(UserPassesTestMixin, ListView):
    """
    View de listagem auditável para superusuarios.

    Fluxo HTTP controlado:
    - GET com parametros de auditoria (`auditar`, período, busca, ordenação).
    - Retorna lista paginável/ordenável de eventos de `AuditLog`.
    """

    model = AuditLog
    template_name = "auditoria/audit_log_list.html"
    context_object_name = "logs"
    raise_exception = True
    PERIOD_UNITS = {
        "minuto": 60,
        "hora": 60 * 60,
        "dia": 24 * 60 * 60,
        "semana": 7 * 24 * 60 * 60,
        "mes": 30 * 24 * 60 * 60,
        "ano": 365 * 24 * 60 * 60,
    }
    PERIOD_OPTIONS = (
        ("minuto", "Minuto"),
        ("hora", "Hora"),
        ("dia", "Dia"),
        ("semana", "Semana"),
        ("mes", "Mês"),
        ("ano", "Ano"),
    )
    SORT_FIELDS = {
        "data": ("timestamp",),
        "usuario": ("user__first_name", "user__username"),
        "acao": ("action", "object_repr"),
    }

    def test_func(self):
        """
        Gate de permissão da view.

        Retorno:
        - `bool`: somente superusuario autenticado pode acessar.
        """

        user = self.request.user
        return bool(user and user.is_authenticated and user.is_superuser)

    def _parse_period(self):
        """
        Valida e transforma período informado na querystring.

        Retorno:
        - `(valor:int|None, unidade:str|None, delta|mensagem_erro)`.

        Regra de negócio:
        - período só é aceito com valor positivo e unidade suportada.
        """

        value_raw = self.request.GET.get("periodo_valor", "").strip()
        unit = self.request.GET.get("periodo_unidade", "").strip().lower()
        if not value_raw and not unit:
            return None, None, None
        try:
            value = int(value_raw)
        except (TypeError, ValueError):
            return None, None, "Informe um valor numérico válido para o período."
        if value <= 0:
            return None, None, "O período deve ser maior que zero."
        if unit not in self.PERIOD_UNITS:
            return None, None, "Selecione uma unidade de período válida."
        delta = timedelta(seconds=value * self.PERIOD_UNITS[unit])
        return value, unit, delta

    def get_queryset(self):
        """
        Monta queryset filtrado conforme parâmetros da tela.

        Retorno:
        - `QuerySet[AuditLog]`: resultados auditáveis ou vazio quando
          filtros mínimos não foram fornecidos.

        Consultas ORM relevantes:
        - `select_related("user", "content_type")` evita N+1 na listagem;
        - `annotate(Cast(...))` permite busca textual sobre campos não-texto.
        """

        if self.request.GET.get("auditar") != "1":
            return AuditLog.objects.none()

        periodo_valor, periodo_unidade, periodo_delta = self._parse_period()
        if not periodo_delta:
            return AuditLog.objects.none()

        self._periodo_valor = periodo_valor
        self._periodo_unidade = periodo_unidade
        self._periodo_error = None

        limite_inferior = timezone.now() - periodo_delta
        queryset = (
            AuditLog.objects.select_related("user", "content_type")
            .filter(timestamp__gte=limite_inferior)
            .annotate(
                # Cast para string para unificar busca `icontains` em campos
                # heterogêneos (datetime/json) sem lógica adicional no template.
                timestamp_text=Cast("timestamp", output_field=models.CharField()),
                changes_text=Cast("changes", output_field=models.CharField()),
            )
        )

        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                models.Q(timestamp_text__icontains=termo)
                | models.Q(user__username__icontains=termo)
                | models.Q(user__first_name__icontains=termo)
                | models.Q(user__last_name__icontains=termo)
                | models.Q(action__icontains=termo)
                | models.Q(content_type__model__icontains=termo)
                | models.Q(object_repr__icontains=termo)
                | models.Q(changes_text__icontains=termo)
            )

        sort = self.request.GET.get("sort", "data")
        direction = self.request.GET.get("dir", "desc")
        if sort not in self.SORT_FIELDS:
            sort = "data"
        if direction not in {"asc", "desc"}:
            direction = "desc"
        order_fields = list(self.SORT_FIELDS[sort])
        if direction == "desc":
            order_fields = [f"-{field}" for field in order_fields]
        queryset = queryset.order_by(*order_fields)

        self._sort = sort
        self._dir = direction
        self._q = termo
        return queryset

    def _sort_link(self, field):
        """
        Gera querystring de ordenação alternando direção atual.

        Parâmetros:
        - `field`: campo lógico de ordenação solicitado.

        Retorno:
        - `str`: querystring pronta para links de cabeçalho.
        """

        query = self.request.GET.copy()
        current_sort = getattr(self, "_sort", "data")
        current_dir = getattr(self, "_dir", "desc")
        next_dir = "asc"
        if current_sort == field and current_dir == "asc":
            next_dir = "desc"
        query["sort"] = field
        query["dir"] = next_dir
        return query.urlencode()

    def get_context_data(self, **kwargs):
        """
        Enriquecimento de contexto para renderização dos controles da tela.

        Parâmetros:
        - `**kwargs`: contexto-base da `ListView`.

        Retorno:
        - `dict`: contexto com estado atual de filtros, ordenação e mensagens.
        """

        context = super().get_context_data(**kwargs)
        periodo_valor, periodo_unidade, periodo_delta = self._parse_period()
        context["periodo_valor"] = periodo_valor or ""
        context["periodo_unidade"] = periodo_unidade or "dia"
        context["periodo_opcoes"] = self.PERIOD_OPTIONS
        context["audit_ran"] = self.request.GET.get("auditar") == "1"
        context["audit_error"] = None
        if context["audit_ran"] and not periodo_delta:
            context["audit_error"] = "Preencha período e unidade válidos para executar a auditoria."
        context["q"] = getattr(self, "_q", self.request.GET.get("q", "").strip())
        context["sort"] = getattr(self, "_sort", self.request.GET.get("sort", "data"))
        context["dir"] = getattr(self, "_dir", self.request.GET.get("dir", "desc"))
        context["sort_links"] = {
            "data": self._sort_link("data"),
            "usuario": self._sort_link("usuario"),
            "acao": self._sort_link("acao"),
        }
        return context
