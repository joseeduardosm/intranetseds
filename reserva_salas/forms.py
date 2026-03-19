"""
Formulários do app `reserva_salas`.

Este módulo centraliza a camada de entrada e validação de dados vindos das views
HTML. Na arquitetura Django:
- `views.py` usa estes formulários em Create/UpdateView;
- `models.py` fornece os campos persistidos e relacionamentos;
- templates de formulário exibem campos e mensagens de erro geradas aqui.

As regras de negócio mais sensíveis (capacidade da sala, recursos solicitados,
conflitos de agenda e recorrência) ficam concentradas em `ReservaForm.clean()`.
"""

import calendar
from datetime import date, timedelta

from django import forms

from .models import Reserva, Sala


class SalaSelect(forms.Select):
    """
    Widget customizado para exibir salas com metadados de cor.

    Papel na arquitetura:
    - Enriquecer o `<option>` do campo de sala para que o frontend possa aplicar
      destaque visual consistente com a cor cadastrada da sala.
    """

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """
        Injeta atributos HTML adicionais no option da sala.

        Parâmetros:
        - mesmos parâmetros do `forms.Select.create_option` do Django.

        Retorno:
        - `dict`: estrutura do option com `data-color` e estilo inline quando
          houver cor definida na instância da sala.
        """
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        instance = getattr(value, "instance", None)
        if instance and getattr(instance, "cor", None):
            option["attrs"]["data-color"] = instance.cor
            option["attrs"]["style"] = f"color: {instance.cor};"
        return option


class SalaForm(forms.ModelForm):
    """
    Formulário de cadastro/edição da entidade `Sala`.

    Papel na arquitetura:
    - Expor no frontend apenas campos relevantes para gestão de infraestrutura,
      incluindo recursos disponíveis para uso em reservas.
    """

    class Meta:
        model = Sala
        fields = [
            "nome",
            "capacidade",
            "localizacao",
            "televisao",
            "projetor",
            "som",
            "microfone_evento",
            "som_evento",
            "mesa_som_evento",
            "videowall",
            "wifi",
        ]
        widgets = {
            # Evita valores inválidos (zero/negativos) já na interface.
            "capacidade": forms.NumberInput(attrs={"min": 1}),
        }


class ReservaForm(forms.ModelForm):
    """
    Formulário de criação/edição de reservas com suporte a recorrência.

    Papel na arquitetura:
    - Traduz dados da agenda para entidade `Reserva` e valida regras temporais,
      capacidade da sala e compatibilidade de recursos.
    """

    sala = forms.ModelChoiceField(queryset=Sala.objects.all(), widget=SalaSelect)
    recorrencia = forms.ChoiceField(
        choices=[
            ("", "Sem recorrência"),
            ("daily", "Diária"),
            ("weekly", "Semanal"),
            ("biweekly", "Quinzenal"),
            ("monthly", "Mensal"),
        ],
        required=False,
        label="Recorrência",
    )
    recorrencia_fim = forms.DateField(
        required=False,
        label="Data fim da recorrência",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Reserva
        fields = [
            "sala",
            "data",
            "hora_inicio",
            "hora_fim",
            "nome_evento",
            "responsavel_evento",
            "quantidade_pessoas",
            "televisao",
            "projetor",
            "som",
            "microfone_evento",
            "som_evento",
            "mesa_som_evento",
            "videowall",
            "wifi",
        ]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_inicio": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_fim": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "quantidade_pessoas": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, **kwargs):
        """
        Configura rótulos e formatos dos campos na inicialização do formulário.

        Regras de negócio aplicadas:
        - Em edição de reserva existente, recorrência fica desabilitada para evitar
          redefinição da série por este formulário.
        - Campos de data/hora são normalizados para o formato esperado no HTML5.
        """
        super().__init__(*args, **kwargs)
        self.fields["sala"].label_from_instance = (
            lambda sala: f"{sala.nome} - {sala.localizacao}"
        )
        self.fields["data"].input_formats = ["%Y-%m-%d"]
        self.fields["hora_inicio"].input_formats = ["%H:%M"]
        self.fields["hora_fim"].input_formats = ["%H:%M"]
        if self.instance and self.instance.pk:
            if self.instance.data:
                self.initial["data"] = self.instance.data.strftime("%Y-%m-%d")
            if self.instance.hora_inicio:
                self.initial["hora_inicio"] = self.instance.hora_inicio.strftime("%H:%M")
            if self.instance.hora_fim:
                self.initial["hora_fim"] = self.instance.hora_fim.strftime("%H:%M")
            self.fields["recorrencia"].disabled = True
            self.fields["recorrencia_fim"].disabled = True

    def is_recurring_series(self) -> bool:
        """
        Indica se a reserva atual pertence a uma série recorrente.

        Retorno:
        - `bool`: `True` quando o registro possui `serie_id`.
        """
        return bool(self.instance and self.instance.pk and self.instance.serie_id)

    def _add_months(self, base_date: date, months: int) -> date:
        """
        Soma meses a uma data preservando o dia quando possível.

        Problema que resolve:
        - Em recorrência mensal, trata corretamente meses com menos dias
          (ex.: reserva dia 31 vira dia 30/28 conforme calendário).

        Parâmetros:
        - `base_date` (`date`): data de referência.
        - `months` (`int`): quantidade de meses a somar.

        Retorno:
        - `date`: data ajustada para o novo mês.
        """
        year = base_date.year + (base_date.month - 1 + months) // 12
        month = (base_date.month - 1 + months) % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(base_date.day, last_day)
        return date(year, month, day)

    def get_recurrence_dates(self):
        """
        Calcula todas as datas de ocorrência conforme regra de recorrência.

        Regras de negócio:
        - Sem recorrência: retorna somente a data inicial.
        - Recorrência sem data de fim: mantém uma única ocorrência.
        - Recorrência com data de fim: gera série até `recorrencia_fim` (inclusive).

        Retorno:
        - `list[date]`: conjunto de datas da série.
        """
        data = self.cleaned_data.get("data")
        recorrencia = self.cleaned_data.get("recorrencia") or ""
        recorrencia_fim = self.cleaned_data.get("recorrencia_fim")
        if not data or not recorrencia:
            return [data] if data else []
        if not recorrencia_fim:
            return [data]
        dates = [data]
        current = data
        if recorrencia == "daily":
            delta = timedelta(days=1)
            while True:
                current = current + delta
                if current > recorrencia_fim:
                    break
                dates.append(current)
        elif recorrencia == "weekly":
            delta = timedelta(days=7)
            while True:
                current = current + delta
                if current > recorrencia_fim:
                    break
                dates.append(current)
        elif recorrencia == "biweekly":
            delta = timedelta(days=14)
            while True:
                current = current + delta
                if current > recorrencia_fim:
                    break
                dates.append(current)
        elif recorrencia == "monthly":
            while True:
                current = self._add_months(current, 1)
                if current > recorrencia_fim:
                    break
                dates.append(current)
        return dates

    def clean(self):
        """
        Executa validações de negócio para garantir consistência da agenda.

        Problemas que resolve:
        - Impede recorrência inválida em edição.
        - Garante coerência entre data inicial e data fim da recorrência.
        - Impede lotação acima da capacidade da sala.
        - Impede solicitação de recurso indisponível na sala.
        - Impede horário de fim menor/igual ao início.
        - Impede conflito de intervalo com reservas existentes.

        Consulta ORM:
        - Para cada data de ocorrência, busca reservas da mesma sala/data e exclui
          o próprio registro em edição para detectar sobreposição de horários.

        Retorno:
        - `dict`: `cleaned_data` (com erros agregados via `add_error` quando houver).
        """
        cleaned = super().clean()
        sala = cleaned.get("sala")
        data = cleaned.get("data")
        hora_inicio = cleaned.get("hora_inicio")
        hora_fim = cleaned.get("hora_fim")
        quantidade = cleaned.get("quantidade_pessoas")
        recorrencia = cleaned.get("recorrencia") or ""
        recorrencia_fim = cleaned.get("recorrencia_fim")

        if self.instance and self.instance.pk and recorrencia:
            self.add_error("recorrencia", "Recorrência só pode ser definida na criação.")

        if recorrencia and not recorrencia_fim:
            self.add_error(
                "recorrencia_fim",
                "Informe a data fim para usar recorrência.",
            )
        if recorrencia and data and recorrencia_fim and recorrencia_fim < data:
            self.add_error(
                "recorrencia_fim",
                "A data fim deve ser maior ou igual à data inicial.",
            )

        if sala and quantidade and quantidade > sala.capacidade:
            self.add_error(
                "quantidade_pessoas",
                "Quantidade de pessoas excede a capacidade da sala.",
            )

        if sala:
            recursos = [
                ("televisao", "Televisao"),
                ("projetor", "Projetor"),
                ("som", "Som"),
                ("microfone_evento", "Microfone (evento)"),
                ("som_evento", "Som (evento)"),
                ("mesa_som_evento", "Mesa de som (evento)"),
                ("videowall", "Videowall"),
                ("wifi", "Wi-Fi"),
            ]
            for campo, _label in recursos:
                # Garante aderência entre necessidade do evento e infraestrutura
                # efetivamente disponível na sala selecionada.
                if cleaned.get(campo) and not getattr(sala, campo):
                    self.add_error(
                        campo,
                        "Recurso nao disponivel na sala selecionada.",
                    )

        if hora_inicio and hora_fim and hora_fim <= hora_inicio:
            self.add_error("hora_fim", "Hora de fim deve ser maior que a hora de inicio.")

        if sala and data and hora_inicio and hora_fim:
            dates = self.get_recurrence_dates() or [data]
            # Compara intervalos em minutos para simplificar detecção de
            # sobreposição entre reservas no mesmo dia/sala.
            inicio_min = hora_inicio.hour * 60 + hora_inicio.minute
            fim_min = hora_fim.hour * 60 + hora_fim.minute
            for occ_date in dates:
                conflitos = (
                    Reserva.objects.filter(sala=sala, data=occ_date)
                    .exclude(pk=self.instance.pk)
                    .all()
                )
                for reserva in conflitos:
                    r_inicio = reserva.hora_inicio.hour * 60 + reserva.hora_inicio.minute
                    r_fim = reserva.hora_fim.hour * 60 + reserva.hora_fim.minute
                    # Regra de interseção de intervalos semiabertos:
                    # [inicio, fim) conflita com [r_inicio, r_fim) quando
                    # inicio < r_fim e fim > r_inicio.
                    if inicio_min < r_fim and fim_min > r_inicio:
                        self.add_error(
                            "hora_inicio",
                            "Ja existe uma reserva para este horario.",
                        )
                        return cleaned

        return cleaned
