"""
Camada de apresentação e orquestração HTTP do app `folha_ponto`.

Integração arquitetural:
- lê dados dos modelos (`Feriado`, `FeriasServidor`, `ConfiguracaoRH`);
- usa formulários para validação de entrada nas telas administrativas;
- renderiza templates do app para emissão da folha de ponto mensal e manutenção RH;
- aplica regras de permissão com base no sistema de auth do Django.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from ramais.models import PessoaRamal

from .forms import ConfiguracaoRHForm, FeriadoForm, FeriasServidorForm
from .models import ConfiguracaoRH, Feriado, FeriasServidor


MESES_PT = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _add_months(base: date, delta: int) -> date:
    """Calcula o primeiro dia do mês deslocado por `delta`.

    Parâmetros:
    - `base`: data de referência (o dia é ignorado no retorno).
    - `delta`: quantidade de meses para frente/para trás.

    Retorno:
    - `date` representando o dia 1 do mês calculado.
    """

    month = base.month - 1 + delta
    year = base.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _can_manage_rh(user) -> bool:
    """Verifica se o usuário pode acessar funcionalidades administrativas de RH.

    Parâmetros:
    - `user`: instância autenticada (ou anônima) do Django auth.

    Retorno:
    - `True` quando possui perfil superusuário ou alguma permissão do app.
    - `False` em qualquer outro cenário.
    """

    return user.is_authenticated and (
        user.is_superuser
        or user.has_perm("folha_ponto.add_feriado")
        or user.has_perm("folha_ponto.change_feriado")
        or user.has_perm("folha_ponto.delete_feriado")
        or user.has_perm("folha_ponto.add_feriasservidor")
        or user.has_perm("folha_ponto.change_feriasservidor")
        or user.has_perm("folha_ponto.delete_feriasservidor")
        or user.has_perm("folha_ponto.change_configuracaorh")
    )


def _get_rh_config() -> ConfiguracaoRH:
    """Obtém a configuração global de RH, criando registro padrão quando ausente.

    Regra de negócio:
    - O app trabalha com configuração singleton (primeiro registro da tabela).
    """

    config = ConfiguracaoRH.objects.first()
    if config is None:
        config = ConfiguracaoRH.objects.create()
    return config


class RHAccessMixin(UserPassesTestMixin):
    """Mixin de autorização para restringir telas administrativas de RH."""

    def test_func(self):
        """Executa o gate de acesso baseado em permissões do usuário logado."""

        return _can_manage_rh(self.request.user)


class FolhaPontoHomeView(LoginRequiredMixin, TemplateView):
    """Controla a tela inicial do módulo, com seleção de competência mensal."""

    template_name = "folha_ponto/home.html"

    def get_context_data(self, **kwargs):
        """Monta contexto com meses navegáveis e flag de gestão RH.

        Retorno:
        - dicionário de template contendo opções de mês anterior/atual/próximo.
        """

        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_options = []
        for delta in (-1, 0, 1):
            dt = _add_months(today.replace(day=1), delta)
            month_options.append(
                {
                    "mes": dt.month,
                    "ano": dt.year,
                    "label": f"{MESES_PT[dt.month - 1]}/{dt.year}",
                }
            )
        context["month_options"] = month_options
        context["can_manage_rh"] = _can_manage_rh(self.request.user)
        return context


@dataclass
class DiaLinha:
    """DTO de uma linha da folha diária impressa.

    Esta estrutura desacopla a lógica de consolidação de dados da camada de template.
    """

    dia: str
    tipo: str
    entrada_hora: str = ""
    entrada_assinatura: str = ""
    saida_hora: str = ""
    saida_assinatura: str = ""
    observacoes: str = ""


class FolhaPontoPrintView(LoginRequiredMixin, TemplateView):
    """Controla o fluxo de geração da folha ponto para impressão mensal."""

    template_name = "folha_ponto/folha_print.html"

    def _get_profile(self):
        """Busca perfil de ramal do usuário autenticado.

        ORM:
        - `select_related("usuario")` evita consulta adicional ao acessar dados do usuário.
        """

        return PessoaRamal.objects.select_related("usuario").filter(usuario=self.request.user).first()

    def _dias_mes(self, ano: int, mes: int, profile: PessoaRamal):
        """Consolida as linhas diárias da folha considerando feriado, férias e fim de semana.

        Parâmetros:
        - `ano`, `mes`: competência da folha.
        - `profile`: servidor para o qual a folha será montada.

        Retorno:
        - lista de `DiaLinha` na ordem de 1..último dia do mês.
        """

        _, total_dias = calendar.monthrange(ano, mes)
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, total_dias)

        # Consulta todos os feriados da competência e indexa por data para lookup O(1) no loop diário.
        feriados = {
            f.data: f
            for f in Feriado.objects.filter(data__range=(inicio, fim))
        }
        # Busca intervalos de férias que intersectam o mês para checar sobreposição por dia.
        ferias = list(
            FeriasServidor.objects.filter(
                servidor=profile,
                data_inicio__lte=fim,
                data_fim__gte=inicio,
            )
        )

        linhas = []
        for dia in range(1, total_dias + 1):
            atual = date(ano, mes, dia)
            weekday = atual.weekday()

            if atual in feriados:
                descricao_feriado = (feriados[atual].descricao or "").upper()
                linhas.append(
                    DiaLinha(
                        dia=str(dia),
                        tipo="feriado",
                        entrada_hora="--------",
                        entrada_assinatura=descricao_feriado,
                        saida_hora="--------",
                        saida_assinatura=descricao_feriado,
                        observacoes="",
                    )
                )
                continue

            ferias_hit = next((fx for fx in ferias if fx.data_inicio <= atual <= fx.data_fim), None)
            if ferias_hit:
                linhas.append(
                    DiaLinha(
                        dia=str(dia),
                        tipo="ferias",
                        entrada_hora="--------",
                        entrada_assinatura="FERIAS",
                        saida_hora="--------",
                        saida_assinatura="FERIAS",
                        observacoes="",
                    )
                )
                continue

            if weekday == 5:
                linhas.append(
                    DiaLinha(
                        dia=str(dia),
                        tipo="sabado",
                        entrada_hora="--------",
                        entrada_assinatura="SABADO",
                        saida_hora="--------",
                        saida_assinatura="SABADO",
                    )
                )
                continue
            if weekday == 6:
                linhas.append(
                    DiaLinha(
                        dia=str(dia),
                        tipo="domingo",
                        entrada_hora="--------",
                        entrada_assinatura="DOMINGO",
                        saida_hora="--------",
                        saida_assinatura="DOMINGO",
                    )
                )
                continue

            linhas.append(DiaLinha(dia=str(dia), tipo="util"))

        return linhas

    def _eventos_consolidacao(self, ano: int, mes: int, profile: PessoaRamal):
        """Gera quadro de consolidação (feriados e férias) exibido no rodapé da folha.

        Retorno:
        - lista fixa com 30 linhas (preenchidas com string vazia quando necessário),
          para manter layout estável na impressão.
        """

        inicio = date(ano, mes, 1)
        _, total_dias = calendar.monthrange(ano, mes)
        fim = date(ano, mes, total_dias)

        eventos = []

        # Feriados da competência ordenados para exibição cronológica no quadro.
        feriados = Feriado.objects.filter(data__range=(inicio, fim)).order_by("data")
        for feriado in feriados:
            eventos.append(
                {
                    "data": feriado.data,
                    "texto": f"{feriado.data:%d/%m/%Y} - {feriado.descricao}",
                }
            )

        # Registros de férias que tocam o mês, com ordenação por início para narrativa temporal.
        ferias = FeriasServidor.objects.filter(
            servidor=profile,
            data_inicio__lte=fim,
            data_fim__gte=inicio,
        ).order_by("data_inicio", "data_fim")
        for registro in ferias:
            de = max(registro.data_inicio, inicio)
            ate = min(registro.data_fim, fim)
            eventos.append(
                {
                    "data": de,
                    "texto": f"{de:%d/%m/%Y} até {ate:%d/%m/%Y} - Férias",
                }
            )

        eventos.sort(key=lambda item: item["data"])
        linhas = [item["texto"] for item in eventos]
        limite_linhas = 30
        if len(linhas) < limite_linhas:
            linhas.extend([""] * (limite_linhas - len(linhas)))
        return linhas[:limite_linhas]

    def get_context_data(self, **kwargs):
        """Monta contexto completo da impressão para mês/ano solicitados via query string.

        Regras relevantes:
        - valida `mes` entre 1 e 12; em erro, usa mês atual;
        - cria automaticamente `PessoaRamal` mínima quando o usuário ainda não tem perfil;
        - injeta dados de jornada, intervalo e lista diária consolidada.
        """

        context = super().get_context_data(**kwargs)
        try:
            ano = int(self.request.GET.get("ano", ""))
            mes = int(self.request.GET.get("mes", ""))
            if mes < 1 or mes > 12:
                raise ValueError
        except ValueError:
            hoje = timezone.localdate()
            ano = hoje.year
            mes = hoje.month

        profile = self._get_profile()
        if profile is None:
            profile = PessoaRamal.objects.create(
                usuario=self.request.user,
                cargo="",
                setor="",
                ramal="",
                email=self.request.user.email or "",
            )

        context["mes_label"] = MESES_PT[mes - 1]
        context["mes"] = mes
        context["ano"] = ano
        context["profile"] = profile
        context["dias"] = self._dias_mes(ano, mes, profile)
        context["jornada_label"] = (
            f"{profile.jornada_horas_semanais} horas" if profile.jornada_horas_semanais else "-"
        )
        context["horario_trabalho_label"] = (
            f"Das {profile.horario_trabalho_inicio:%H:%M} ate {profile.horario_trabalho_fim:%H:%M}"
            if profile.horario_trabalho_inicio and profile.horario_trabalho_fim
            else "-"
        )
        context["intervalo_label"] = (
            f"Das {profile.intervalo_inicio:%H:%M} ate {profile.intervalo_fim:%H:%M}"
            if profile.intervalo_inicio and profile.intervalo_fim
            else "-"
        )
        context["regime_plantao_label"] = "S" if profile.regime_plantao else "N"
        context["horario_estudante_label"] = "S" if profile.horario_estudante else "N"
        context["hoje"] = timezone.localdate()
        context["eventos_consolidacao"] = self._eventos_consolidacao(ano, mes, profile)
        rh_config = ConfiguracaoRH.objects.first()
        context["brasao_url"] = rh_config.brasao.url if rh_config and rh_config.brasao else None
        return context


class RHBrasaoView(RHAccessMixin, View):
    """Controla manutenção do brasão institucional usado na folha impressa."""

    template_name = "folha_ponto/brasao_form.html"

    def get(self, request):
        """Renderiza formulário com configuração RH atual para edição."""

        form = ConfiguracaoRHForm(instance=_get_rh_config())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        """Processa upload do brasão e persiste configuração quando válida.

        Fluxo:
        - valida arquivo pelo `ConfiguracaoRHForm`;
        - em sucesso, redireciona para área administrativa de RH.
        """

        config = _get_rh_config()
        form = ConfiguracaoRHForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            return redirect("administracao_rh")
        return render(request, self.template_name, {"form": form})


class FeriadoListView(RHAccessMixin, ListView):
    """Lista feriados cadastrados para gestão de calendário de RH."""

    model = Feriado
    template_name = "folha_ponto/feriado_list.html"
    context_object_name = "feriados"


class FeriadoCreateView(RHAccessMixin, PermissionRequiredMixin, CreateView):
    """Controla requisição HTTP de criação de feriado (GET formulário / POST persistência)."""

    model = Feriado
    form_class = FeriadoForm
    template_name = "folha_ponto/feriado_form.html"
    success_url = reverse_lazy("folha_ponto_feriado_list")
    permission_required = "folha_ponto.add_feriado"


class FeriadoUpdateView(RHAccessMixin, PermissionRequiredMixin, UpdateView):
    """Controla edição de registro de feriado existente."""

    model = Feriado
    form_class = FeriadoForm
    template_name = "folha_ponto/feriado_form.html"
    success_url = reverse_lazy("folha_ponto_feriado_list")
    permission_required = "folha_ponto.change_feriado"


class FeriadoDeleteView(RHAccessMixin, PermissionRequiredMixin, DeleteView):
    """Controla confirmação e remoção de feriado."""

    model = Feriado
    template_name = "folha_ponto/feriado_confirm_delete.html"
    success_url = reverse_lazy("folha_ponto_feriado_list")
    permission_required = "folha_ponto.delete_feriado"


class FeriasListView(RHAccessMixin, ListView):
    """Lista lançamentos de férias dos servidores."""

    model = FeriasServidor
    template_name = "folha_ponto/ferias_list.html"
    context_object_name = "ferias"


class FeriasCreateView(RHAccessMixin, PermissionRequiredMixin, CreateView):
    """Controla criação de períodos de férias via formulário administrativo."""

    model = FeriasServidor
    form_class = FeriasServidorForm
    template_name = "folha_ponto/ferias_form.html"
    success_url = reverse_lazy("folha_ponto_ferias_list")
    permission_required = "folha_ponto.add_feriasservidor"

    def form_valid(self, form):
        """Anexa usuário logado como autor do lançamento antes de salvar.

        Parâmetros:
        - `form`: formulário já validado.

        Retorno:
        - resposta HTTP de sucesso padrão do `CreateView`.
        """

        form.instance.criado_por = self.request.user
        return super().form_valid(form)


class FeriasUpdateView(RHAccessMixin, PermissionRequiredMixin, UpdateView):
    """Controla edição de um lançamento de férias existente."""

    model = FeriasServidor
    form_class = FeriasServidorForm
    template_name = "folha_ponto/ferias_form.html"
    success_url = reverse_lazy("folha_ponto_ferias_list")
    permission_required = "folha_ponto.change_feriasservidor"


class FeriasDeleteView(RHAccessMixin, PermissionRequiredMixin, DeleteView):
    """Controla confirmação e exclusão de lançamento de férias."""

    model = FeriasServidor
    template_name = "folha_ponto/ferias_confirm_delete.html"
    success_url = reverse_lazy("folha_ponto_ferias_list")
    permission_required = "folha_ponto.delete_feriasservidor"
