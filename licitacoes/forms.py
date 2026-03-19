"""
Formulários e regras de validação de entrada do app `licitacoes`.

Integração arquitetural:
- converte payload HTTP das views em dados validados;
- aplica normalizações de texto para manter padrão jurídico de enumeração;
- define widgets e labels para templates de manutenção do TR.
"""

from django import forms
import re

from .models import EtpTic, ItemSessao, SessaoTermo, SubsessaoTermo, TabelaItemLinha, TermoReferencia


ROMAN_ENUM_RE = re.compile(r"^\s*([IVXLCDM]+)\s*[\)\.\-–—]\s*(.+?)\s*$")
ALPHA_ENUM_RE = re.compile(r"^\s*([a-z])\)\s*(.+?)\s*$", re.IGNORECASE)


def _lower_first_alpha(texto: str) -> str:
    """Converte apenas a primeira letra alfabética para minúscula.

    Uso:
    - padronizar início de incisos/alíneas durante normalização textual.
    """

    for idx, ch in enumerate(texto):
        if ch.isalpha():
            return texto[:idx] + ch.lower() + texto[idx + 1 :]
    return texto


def _normalize_enum_block(lines: list[str], pattern: re.Pattern[str], marker_fmt: str) -> list[str]:
    """Normaliza bloco homogêneo de enumeração (incisos ou alíneas).

    Parâmetros:
    - `lines`: linhas candidatas do bloco.
    - `pattern`: regex de identificação da enumeração.
    - `marker_fmt`: formato de marcador (`{}`) para reconstrução.

    Retorno:
    - lista normalizada, com final `;` para intermediárias e `.` para última linha.
    """

    matches = []
    for line in lines:
        m = pattern.match(line)
        if not m:
            return lines
        matches.append(m)

    normalized: list[str] = []
    last_idx = len(matches) - 1
    for idx, m in enumerate(matches):
        marker = m.group(1)
        corpo = (m.group(2) or "").strip()
        corpo = _lower_first_alpha(corpo)
        corpo = re.sub(r"[;:.,\s]+$", "", corpo)
        fim = "." if idx == last_idx else ";"
        normalized.append(f"{marker_fmt.format(marker)} {corpo}{fim}")
    return normalized


def _normalize_alineas_incisos(texto: str) -> str:
    """Padroniza blocos de incisos/alíneas em texto livre de item.

    Regra de negócio:
    - quando identifica sequência enumerada, força separador por `:` no trecho anterior;
    - preserva linhas não enumeradas sem intervenção.
    """

    raw_lines = texto.splitlines()
    lines = [line.rstrip() for line in raw_lines]
    out: list[str] = []
    i = 0
    while i < len(lines):
        current = lines[i].strip()
        if not current:
            out.append("")
            i += 1
            continue

        # Detecta bloco de incisos romanos.
        if ROMAN_ENUM_RE.match(current):
            j = i
            block: list[str] = []
            while j < len(lines) and lines[j].strip() and ROMAN_ENUM_RE.match(lines[j].strip()):
                block.append(lines[j].strip())
                j += 1
            if out:
                prev = out[-1].rstrip()
                if prev and not prev.endswith(":"):
                    out[-1] = prev + ":"
            out.extend(_normalize_enum_block(block, ROMAN_ENUM_RE, "{} )".replace(" ", "")))
            i = j
            continue

        # Detecta bloco de alineas a), b), c)...
        if ALPHA_ENUM_RE.match(current):
            j = i
            block = []
            while j < len(lines) and lines[j].strip() and ALPHA_ENUM_RE.match(lines[j].strip()):
                block.append(lines[j].strip())
                j += 1
            if out:
                prev = out[-1].rstrip()
                if prev and not prev.endswith(":"):
                    out[-1] = prev + ":"
            out.extend(_normalize_enum_block(block, ALPHA_ENUM_RE, "{})"))
            i = j
            continue

        out.append(lines[i].rstrip())
        i += 1

    return "\n".join(out).strip()


def _normalize_soft_linebreaks(texto: str) -> str:
    """Remove quebras artificiais dentro do mesmo parágrafo.

    Regras:
    - une linhas corridas em um único parágrafo;
    - preserva linhas em branco entre parágrafos;
    - mantém quebra entre itens enumerados, mas junta continuações do mesmo item.
    """

    normalized_lines: list[str] = []
    current_parts: list[str] = []
    current_is_enum = False

    def flush_current() -> None:
        nonlocal current_parts, current_is_enum
        if current_parts:
            normalized_lines.append(" ".join(current_parts).strip())
            current_parts = []
            current_is_enum = False

    for raw_line in (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_current()
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue

        is_enum_line = bool(ROMAN_ENUM_RE.match(line) or ALPHA_ENUM_RE.match(line))
        if not current_parts:
            current_parts = [line]
            current_is_enum = is_enum_line
            continue

        if is_enum_line:
            flush_current()
            current_parts = [line]
            current_is_enum = True
            continue

        current_parts.append(line)
        if not current_is_enum:
            current_is_enum = False

    flush_current()
    return "\n".join(normalized_lines).strip()


class TermoReferenciaForm(forms.ModelForm):
    """Formulário principal de criação/edição de metadados do TR."""

    class Meta:
        """Expõe apenas os campos de identificação do termo."""

        model = TermoReferencia
        fields = ["apelido", "processo_sei", "link_processo_sei"]


class SessaoTermoForm(forms.ModelForm):
    """Formulário de manutenção de título de sessão do termo."""

    class Meta:
        """Configura campo único necessário para sessão."""

        model = SessaoTermo
        fields = ["titulo"]


class ItemSessaoForm(forms.ModelForm):
    """Formulário de item/subitem, com normalização textual específica do TR."""

    class Meta:
        """Define campos e widget de edição extensa para conteúdo do item."""

        model = ItemSessao
        fields = ["subsessao", "texto"]
        widgets = {
            "texto": forms.Textarea(
                attrs={
                    "rows": 24,
                    "style": "min-height: 62vh; resize: vertical;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Restringe queryset de `subsessao` ao contexto da sessão corrente.

        Parâmetros:
        - `sessao` opcional em `kwargs` para filtrar apenas subseções válidas.
        """

        sessao = kwargs.pop("sessao", None)
        super().__init__(*args, **kwargs)
        self.fields["subsessao"].required = False
        if sessao is not None:
            self.fields["subsessao"].queryset = SubsessaoTermo.objects.filter(sessao=sessao).order_by("ordem", "id")
        else:
            self.fields["subsessao"].queryset = SubsessaoTermo.objects.none()

    def clean_texto(self):
        """Normaliza texto inserido no item removendo numeração redundante.

        Retorno:
        - conteúdo limpo para persistência, com tratamento de incisos/alíneas.
        """

        texto = (self.cleaned_data.get("texto") or "").strip()
        texto = _normalize_soft_linebreaks(texto)
        # Remove indice no inicio, ex.: "7.1 ", "7.2.3 ", "7.1. ".
        texto = re.sub(r"^\s*\d+(?:\.\d+)+(?:\.)?\s*[-–—:]?\s*", "", texto)
        # Remove marcador manual de inciso/alinea no inicio, ex.: "I) ", "a) ".
        texto = re.sub(r"^\s*(?:[IVXLCDM]+|[a-z])\)\s*", "", texto, flags=re.IGNORECASE)
        texto = _normalize_alineas_incisos(texto)
        return texto


class SubsessaoTermoForm(forms.ModelForm):
    """Formulário de cadastro/edição de subseções."""

    class Meta:
        """Define campos permitidos para subseção."""

        model = SubsessaoTermo
        fields = ["titulo"]


class TabelaItemLinhaForm(forms.ModelForm):
    """Formulário de linha de tabela vinculada ao item 1.1 do TR."""

    class Meta:
        """Define campos de descrição/códigos/unidade/quantidade da linha."""

        model = TabelaItemLinha
        fields = [
            "descricao",
            "catmat_catser",
            "siafisico",
            "unidade_fornecimento",
            "quantidade",
        ]
        widgets = {
            "descricao": forms.Textarea(
                attrs={
                    "rows": 14,
                    "style": "min-height: 38vh; resize: vertical;",
                }
            ),
        }


class TermoReferenciaDuplicarForm(forms.Form):
    """Formulário simples para informar novo apelido na duplicação de TR."""

    novo_apelido = forms.CharField(label="Novo nome do TR", max_length=180)


class TermoReferenciaImportarForm(forms.Form):
    """Formulário de importação estrutural de termo por DOCX ou texto colado."""

    apelido = forms.CharField(label="Apelido do TR", max_length=180)
    arquivo = forms.FileField(label="Arquivo DOCX", required=False)
    texto = forms.CharField(
        label="Texto colado do Word",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 20,
                "style": "min-height: 48vh; resize: vertical;",
                "placeholder": "Cole aqui o conteudo do Word para importar por texto.",
            }
        ),
    )

    def clean(self):
        """Validação de regra cruzada: exige ao menos uma fonte de importação.

        Retorno:
        - dicionário `cleaned_data` válido para continuidade do fluxo.
        """

        cleaned = super().clean()
        arquivo = cleaned.get("arquivo")
        texto = (cleaned.get("texto") or "").strip()
        if not arquivo and not texto:
            raise forms.ValidationError("Informe um arquivo .docx ou cole o texto do Word.")
        return cleaned

    def clean_arquivo(self):
        """Valida extensão do arquivo quando fornecido pelo usuário.

        Retorno:
        - objeto de arquivo aceito ou erro de validação para formato inválido.
        """

        arquivo = self.cleaned_data.get("arquivo")
        if not arquivo:
            return arquivo
        nome = (arquivo.name or "").lower()
        if not nome.endswith(".docx"):
            raise forms.ValidationError("Envie um arquivo no formato .docx.")
        return arquivo


class EtpTicCreateForm(forms.ModelForm):
    """Criação inicial do ETP TIC com metadados mínimos."""

    class Meta:
        model = EtpTic
        fields = ["titulo", "numero_processo_servico"]


class EtpTicSecaoForm(forms.ModelForm):
    """Form de edição de uma seção específica do ETP TIC."""

    class Meta:
        model = EtpTic
        fields = "__all__"
        widgets = {
            "descricao_necessidade": forms.Textarea(attrs={"rows": 12}),
            "necessidades_negocio": forms.Textarea(attrs={"rows": 12}),
            "necessidades_tecnologicas": forms.Textarea(attrs={"rows": 12}),
            "demais_requisitos": forms.Textarea(attrs={"rows": 12}),
            "estimativa_demanda": forms.Textarea(attrs={"rows": 12}),
            "levantamento_solucoes": forms.Textarea(attrs={"rows": 12}),
            "analise_comparativa_solucoes": forms.Textarea(attrs={"rows": 12}),
            "solucoes_inviaveis": forms.Textarea(attrs={"rows": 12}),
            "analise_comparativa_custos_tco": forms.Textarea(attrs={"rows": 12}),
            "descricao_solucao_tic": forms.Textarea(attrs={"rows": 12}),
            "estimativa_custo_texto": forms.Textarea(attrs={"rows": 12}),
            "justificativa_tecnica": forms.Textarea(attrs={"rows": 12}),
            "justificativa_economica": forms.Textarea(attrs={"rows": 12}),
            "beneficios_contratacao": forms.Textarea(attrs={"rows": 12}),
            "providencias_adotadas": forms.Textarea(attrs={"rows": 12}),
            "declaracao_viabilidade": forms.Textarea(attrs={"rows": 4, "readonly": "readonly"}),
            "justificativa_viabilidade": forms.Textarea(attrs={"rows": 12}),
        }

    def __init__(self, *args, section_fields=None, **kwargs):
        self._section_fields = section_fields or []
        super().__init__(*args, **kwargs)
        allowed = set(self._section_fields)
        for name in list(self.fields.keys()):
            if name not in allowed:
                self.fields.pop(name)
        if "declaracao_viabilidade" in self.fields:
            self.fields["declaracao_viabilidade"].disabled = True
