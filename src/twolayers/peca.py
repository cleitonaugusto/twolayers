"""verificar-peca: checagens locais de uma peça jurídica (PDF, DOCX ou texto) antes do protocolo.

Tudo roda na máquina, sem rede: o documento do cliente não sai do computador.
O que é verificado:
  T1  texto oculto (cor branca, fonte minúscula, fora da página, modo invisível, coberto por retângulo,
      oculto no Word)
  T2  caracteres Unicode invisíveis
  T3  frases dirigidas a uma IA (injeção de prompt)
  C1  números de processo no padrão CNJ com dígito verificador inválido (número impossível)
  C2  súmulas com número acima do maior existente
  C3  inventário de precedentes citados, para conferência humana
  V1–V5  vazamento pelo arquivo: alterações rastreadas, comentários, metadados, versões anteriores, conteúdo
         ativo ou embutido (ver vazamento.py)
"""

import re
import unicodedata
import zipfile
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from . import vazamento
from . import formatacao
from .achados import NA, OK, REVISAR, RISCO, Achado

# ------------------------------------------------------------------ extração


@dataclass
class Trecho:
    texto: str
    pagina: int
    motivo: str = ""  # vazio = visível; senão, por que está oculto
    caixas: list = field(default_factory=list)  # caixas das letras (PDF), para conferir na página desenhada


def _cor_clara(cor, espaco: str) -> bool:
    if cor is None:
        return False
    valores = cor if isinstance(cor, (list, tuple)) else (cor,)
    try:
        valores = [float(v) for v in valores]
    except (TypeError, ValueError):
        return False
    if len(valores) == 4 or "CMYK" in espaco.upper():
        return all(v <= 0.05 for v in valores)
    return all(v >= 0.95 for v in valores)


def _luminancia(cor, espaco: str = "") -> float | None:
    """0 = preto, 1 = branco. None se não der para saber."""
    if cor is None:
        return 0.0  # sem cor definida, o PDF preenche de preto
    valores = cor if isinstance(cor, (list, tuple)) else (cor,)
    try:
        v = [float(x) for x in valores]
    except (TypeError, ValueError):
        return None
    if len(v) == 4 or "CMYK" in espaco.upper():
        c, m, y, k = (v + [0, 0, 0, 0])[:4]
        v = [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    if len(v) == 1:
        return v[0]
    if len(v) == 3:
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    return None


# Forma desenhada POR CIMA do texto só esconde quando é escura (tarja) ou branca (corretivo). Cor clara intermediária
# por cima costuma ser marca-texto com transparência (o leitor de PDF não informa a transparência): o texto aparece.
TARJA_ESCURA, CORRETIVO_BRANCO = 0.35, 0.95
COBERTURA = 0.6  # fração da letra que a forma por cima precisa cobrir
PAGINA_DIGITALIZADA = 0.8  # fração de texto invisível que, com imagens na página, indica página escaneada com OCR
FONTE_MINIMA_PDF = 2.0  # pt; rótulos de mapa e gráfico ficam entre 2 e 3 pt
OCR = "camada de OCR sob imagem digitalizada"
FORA = "fora da área da página"
COBERTO = "coberto por retângulo ou tarja desenhada por cima (continua legível para máquinas)"
BRANCO = "texto em cor branca"
CONFERIVEIS_NA_PAGINA = (BRANCO, COBERTO)  # a leitura estrutural tem dúvida; a página desenhada decide
MINIMO_AVALIADAS = 3  # letras avaliadas na página desenhada para retirar uma acusação


def _para_coordenadas_do_pdf(caixa, rotacao: int, mediabox) -> tuple:
    """O pdfminer entrega as caixas já giradas e deslocadas pela mediabox (begin_page); o motor de desenho usa as
    coordenadas originais da página. Desfaz a mesma transformação."""
    x0m, y0m, x1m, y1m = mediabox
    rot = rotacao % 360

    def ponto(dx, dy):
        if rot == 90:
            return x1m - dy, dx + y0m
        if rot == 180:
            return x1m - dx, y1m - dy
        if rot == 270:
            return dy + x0m, y1m - dx
        return dx + x0m, dy + y0m

    a, b = ponto(caixa[0], caixa[1]), ponto(caixa[2], caixa[3])
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def _fora_do_corte(caixa, rotacao: int, mediabox, corte) -> bool:
    """Centro da letra fora da área de corte (CropBox), em coordenadas do PDF."""
    x0, y0, x1, y1 = _para_coordenadas_do_pdf(caixa, rotacao, mediabox)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return not (corte[0] <= cx <= corte[2] and corte[1] <= cy <= corte[3])


def _conferir_na_pagina(caminho, n: int, trechos: list[Trecho], rotacao: int = 0, mediabox=(0, 0, 0, 0)) -> None:
    """Trecho branco ou coberto que APARECE na página desenhada deixa de ser oculto (a maioria das letras avaliadas
    precisa aparecer). Só retira acusação; o que a página não consegue avaliar fica como estava."""
    from . import render
    alvos = [t for t in trechos if t.motivo in CONFERIVEIS_NA_PAGINA and t.caixas and substancial(t.texto)]
    if not alvos:
        return
    todas = [_para_coordenadas_do_pdf(c, rotacao, mediabox) for t in alvos for c in t.caixas]
    letras = []
    for t in alvos:  # uma letra por caixa; se o extrator juntou letras (ligadura, cid), segue sem a letra
        lt = [ch for ch in t.texto if ch != "\n"]
        letras += lt if len(lt) == len(t.caixas) else [""] * len(t.caixas)
    try:
        vistas = render.visibilidade(caminho, n, todas, letras)
    except Exception:  # motor de desenho falhou neste arquivo: fica a leitura estrutural
        return
    i = 0
    for t in alvos:
        parte = vistas[i:i + len(t.caixas)]
        i += len(t.caixas)
        avaliadas = [v for v in parte if v is not None]
        # decide pelas letras que deu para avaliar (as demais têm outro texto no mesmo lugar), desde que sejam
        # bastantes; onde só a letra suspeita está desenhada, a comparação é segura
        if len(avaliadas) >= max(MINIMO_AVALIADAS, len(parte) / 4) and sum(avaliadas) > len(avaliadas) / 2:
            t.motivo = ""


def extrair_pdf(caminho) -> list[Trecho]:
    """caminho: Path ou arquivo binário já aberto (o V4 lê versões anteriores direto da memória)."""
    try:
        from pdfminer.converter import PDFPageAggregator
        from pdfminer.layout import LAParams, LTChar, LTTextLine
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.pdfpage import PDFPage
    except ImportError as e:  # dependência opcional
        raise RuntimeError("Para ler PDF instale o extra: pip install 'twolayers[pdf]'") from e

    class Agregador(PDFPageAggregator):
        """Guarda o que o layout do pdfminer descarta: modo de renderização do texto e ordem de desenho."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.ordem, self.modo, self.preenchidos, self.imagens = 0, 0, [], []
            self._imagem = False

        def render_string(self, textstate, seq, ncs, graphicstate):
            self.modo = textstate.render
            super().render_string(textstate, seq, ncs, graphicstate)

        def render_char(self, *a, **k):
            adv = super().render_char(*a, **k)
            c = self.cur_item._objs[-1]
            self.ordem += 1
            c.camada_ordem, c.camada_modo = self.ordem, self.modo
            return adv

        def paint_path(self, gstate, stroke, fill, evenodd, path):
            antes = len(self.cur_item._objs)
            super().paint_path(gstate, stroke, fill, evenodd, path)
            self.ordem += 1
            if fill:
                for obj in self.cur_item._objs[antes:]:
                    cor = getattr(obj, "non_stroking_color", None)
                    lum = _luminancia(cor)
                    clara = lum is not None and lum >= CORRETIVO_BRANCO
                    cobre = lum is None or lum < TARJA_ESCURA or lum >= CORRETIVO_BRANCO
                    self.preenchidos.append((self.ordem, obj.bbox, clara, cobre))

        def render_image(self, name, stream):
            super().render_image(name, stream)
            self._imagem = True

        def end_figure(self, name):
            super().end_figure(name)
            if self._imagem and self.cur_item._objs:
                self.ordem += 1
                self.imagens.append((self.ordem, self.cur_item._objs[-1].bbox))
            self._imagem = False

    trechos: list[Trecho] = []

    def caracteres(elemento):
        """Caracteres na ordem do layout; None marca o fim de cada linha."""
        if isinstance(elemento, LTChar):
            yield elemento
        elif hasattr(elemento, "__iter__"):
            for filho in elemento:
                yield from caracteres(filho)
            if isinstance(elemento, LTTextLine):
                yield None

    def fundo_nao_branco(c, preenchidos) -> bool:
        """Forma não branca desenhada ANTES, sob o centro do caractere (texto branco sobre faixa escura é visível)."""
        cx, cy, ordem = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2, getattr(c, "camada_ordem", 0)
        for o, (x0, y0, x1, y1), clara, _ in preenchidos:
            if o < ordem and not clara and x0 <= cx <= x1 and y0 <= cy <= y1:
                return True
        return False

    def coberto(c, cobridores) -> bool:
        """Tarja escura ou corretivo branco desenhado DEPOIS e cobrindo a maior parte da letra (linha fina de
        tabela passa pelo centro, mas não cobre). cobridores: só as formas que podem esconder, separadas por página."""
        ordem = getattr(c, "camada_ordem", 0)
        cx0, cy0, cx1, cy1 = c.x0, c.y0, c.x1, c.y1
        area = max((cx1 - cx0) * (cy1 - cy0), 1e-6)
        for o, (x0, y0, x1, y1) in cobridores:
            if o <= ordem or x1 <= cx0 or x0 >= cx1 or y1 <= cy0 or y0 >= cy1:
                continue
            if (min(x1, cx1) - max(x0, cx0)) * (min(y1, cy1) - max(y0, cy0)) / area >= COBERTURA:
                return True
        return False

    def sobre_imagem(c, imagens, qualquer_ordem: bool = False) -> bool:
        """Imagem no centro do caractere: desenhada antes (fundo: foto, faixa) ou, para OCR, em qualquer ordem
        (há digitalizadores que desenham o texto invisível primeiro e a imagem da página por cima)."""
        cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
        ordem = getattr(c, "camada_ordem", 0)
        return any((qualquer_ordem or o < ordem) and x0 <= cx <= x1 and y0 <= cy <= y1 for o, (x0, y0, x1, y1) in imagens)

    from . import render
    # com o motor de desenho disponível: QUALQUER forma por cima é suspeita e a página desenhada libera o que aparece
    # (marca-texto transparente); sem ele, vale a regra aproximada (só tarja escura ou corretivo branco)
    usar_render = not hasattr(caminho, "read") and render.disponivel()
    gestor = PDFResourceManager()
    dispositivo = Agregador(gestor, laparams=LAParams())
    interpretador = PDFPageInterpreter(gestor, dispositivo)
    with (nullcontext(caminho) if hasattr(caminho, "read") else open(caminho, "rb")) as arq:
        for n, pag in enumerate(PDFPage.get_pages(arq), 1):
            dispositivo.ordem, dispositivo.preenchidos, dispositivo.imagens = 0, [], []
            interpretador.process_page(pag)
            pagina = dispositivo.get_result()
            cobridores = [(o, bbox) for o, bbox, _, cobre in dispositivo.preenchidos if cobre or usar_render]
            inicio_pagina = len(trechos)
            largura, altura = pagina.width, pagina.height
            # área que o leitor de PDF mostra (CropBox); texto fora dela não aparece, mesmo estando dentro da MediaBox
            corte = tuple(pag.cropbox) if pag.cropbox else None
            if corte and tuple(corte) == tuple(pag.mediabox):
                corte = None
            atual, motivo_atual, caixas = [], None, []
            letras = invisiveis = 0
            for c in caracteres(pagina):
                if c is None:
                    atual.append("\n")
                    continue
                gs = c.graphicstate
                espaco = getattr(getattr(gs, "ncs", None), "name", "") or ""
                if corte and _fora_do_corte(c.bbox, pag.rotate or 0, pag.mediabox, corte):
                    motivo = FORA
                elif getattr(c, "camada_modo", 0) in (3, 7):
                    # texto invisível sobre imagem = camada pesquisável de página digitalizada (OCR); continua
                    # passando pela busca de comando para IA, mas não é "texto escondido" por si só
                    motivo = OCR if sobre_imagem(c, dispositivo.imagens, True) else "modo de renderização invisível (Tr 3)"
                elif (_cor_clara(getattr(gs, "ncolor", None), espaco) and not fundo_nao_branco(c, dispositivo.preenchidos)
                      and not sobre_imagem(c, dispositivo.imagens)):
                    motivo = BRANCO
                elif c.size < FONTE_MINIMA_PDF:
                    motivo = f"fonte de {c.size:.1f} pt"
                elif c.x1 < 0 or c.x0 > largura or c.y1 < 0 or c.y0 > altura:
                    motivo = FORA
                elif cobridores and coberto(c, cobridores):
                    motivo = COBERTO
                else:
                    motivo = ""
                if motivo != motivo_atual and atual:
                    trechos.append(Trecho("".join(atual), n, motivo_atual or "", caixas))
                    atual, caixas = [], []
                motivo_atual = motivo
                atual.append(c.get_text())
                if c.get_text().strip():
                    letras += 1
                    invisiveis += getattr(c, "camada_modo", 0) in (3, 7)
                caixas.append(c.bbox)
            if atual:
                trechos.append(Trecho("".join(atual), n, motivo_atual or "", caixas))
            # página digitalizada em recortes (um por bloco de texto): a letra pode cair fora de todos os recortes;
            # se a página tem imagens e quase todo o texto é invisível, o texto invisível dela é a camada de OCR
            if dispositivo.imagens and letras and invisiveis / letras >= PAGINA_DIGITALIZADA:
                for t in trechos[inicio_pagina:]:
                    if t.motivo == "modo de renderização invisível (Tr 3)":
                        t.motivo = OCR
            if usar_render:
                _conferir_na_pagina(caminho, n, trechos[inicio_pagina:], pag.rotate or 0, pag.mediabox)
    return trechos


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extrair_docx(caminho: Path) -> list[Trecho]:
    """Trechos na ordem do documento, com a formatação EFETIVA (estilos + direta) e o contraste com o fundo."""
    trechos: list[Trecho] = []
    with zipfile.ZipFile(caminho) as z:
        nomes = set(z.namelist())
        ler = lambda n: ElementTree.fromstring(z.read(n)) if n in nomes else None  # noqa: E731
        estilos = formatacao.Estilos(ler("word/styles.xml"))
        cor_papel = formatacao.papel(ler("word/document.xml"))
        partes = [p for p in nomes
                  if re.match(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$", p)]
        for parte in sorted(partes):
            for _, runs in formatacao.trechos(ler(parte), estilos, cor_papel):
                for _, texto, _, motivo in runs:
                    if "comments" in parte:
                        motivo = motivo or "comentário do Word"
                    trechos.append(Trecho(texto, 0, motivo))
                trechos.append(Trecho("\n", 0, ""))
    return trechos


WORD = (".docx", ".docm", ".dotx", ".dotm")
TEXTO_PURO = (".txt", ".md")
FORMATOS = (".pdf", *WORD, *TEXTO_PURO)


class FormatoNaoSuportado(ValueError):
    """Formato que a ferramenta não sabe ler de verdade. Melhor recusar do que dizer "nada encontrado" sem ter lido."""


def extrair(caminho: Path) -> list[Trecho]:
    caminho = Path(caminho)
    sufixo = caminho.suffix.lower()
    if sufixo == ".pdf":
        return extrair_pdf(caminho)
    if sufixo in WORD:
        return extrair_docx(caminho)
    if sufixo in TEXTO_PURO:
        return [Trecho(caminho.read_text(encoding="utf-8", errors="replace"), 0, "")]
    # .doc (Word 97-2003), .odt, .rtf etc.: lidos como texto, dariam lixo binário e falsos achados (ou falso "nada")
    raise FormatoNaoSuportado(f"formato {sufixo or '(sem extensão)'} não suportado: salve como PDF ou .docx")


# ------------------------------------------------------------------ verificações

INVISIVEIS = {
    **{chr(c): "espaço/junção de largura zero" for c in (0x200B, 0x200C, 0x200D, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0xFEFF)},
    **{chr(c): "controle de direção de texto" for c in (0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                                                         0x2066, 0x2067, 0x2068, 0x2069)},
    "­": "hífen invisível",
}

INJECAO = [
    re.compile(r"(?i)(se|caso|quando)\s+(est[ea]|o presente|a presente)\s+[\w\s]{0,40}?(for|seja|estiver sendo)\s+"
               r"(lid[oa]|analisad[oa]|processad[oa]|resumid[oa])\s+(por|pel[ao])\s+(uma?\s+)?"
               r"(ia|i\.a\.|inteligência artificial|intelig[eê]ncia artificial|modelo de linguagem|llm|sistema automatizado)"),
    re.compile(r"(?i)\b(ignore|desconsidere|esqueça)\s+(as|todas as|quaisquer)?\s*(instru[çc][õo]es|regras|orienta[çc][õo]es)\s+(anteriores|acima|do sistema)"),
    re.compile(r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b"),
    re.compile(r"(?i)\b(system prompt|prompt do sistema|you are an? (ai|assistant)|voc[eê] [eé] (um|uma) (assistente|ia|modelo))\b"),
    re.compile(r"(?i)\b(ia|intelig[eê]ncia artificial|assistente|modelo)\b[^.\n]{0,80}\b(acolh\w+|defir\w+|julg\w+ procedente|"
               r"favorável|reconhe[çc]\w+ o direito|interprete\w*)\b"),
]

CNJ = re.compile(r"\b(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\b")

# maior número existente (limites generosos; atualizar periodicamente)
SUMULAS_MAX = {"STF": 736, "SV": 70, "STJ": 720, "TST": 480}
SUMULA = re.compile(
    r"(?i)\bs[úu]mula\s+(vinculante\s+)?(?:n[º°o.]*\s*)?(\d{1,3}(?:\.\d{3})+|\d{1,4})(?:[^\n.;]{0,25}?\b(STF|STJ|TST)\b)?")
PRECEDENTE = re.compile(
    r"\b(REsp|AgRg|AgInt|EDcl|RE|ARE|HC|RHC|MS|RMS|ADI|ADPF|ADC|RR|AIRR|Ag|AI|ROT|Rcl)\s*(?:n[º°.]*\s*)?"
    r"(\d{1,3}(?:\.\d{3})+|\d{3,})(?:\s*/\s*[A-Z]{2})?")


def _dv_cnj_valido(n, dv, ano, j, tr, orig) -> bool:
    return int(f"{n}{ano}{j}{tr}{orig}{dv}") % 97 == 1


def _linha(texto: str, pos: int) -> str:
    ini = texto.rfind("\n", 0, pos) + 1
    fim = texto.find("\n", pos)
    return " ".join(texto[ini: fim if fim != -1 else len(texto)].split())[:160]


def _onde(t: Trecho) -> str:
    return f"pág. {t.pagina}" if t.pagina else "documento"


def _decodificar_tags(texto: str) -> str:
    """Caracteres Unicode 'tag' (U+E0020–U+E007E) espelham o ASCII e não aparecem na tela."""
    return "".join(chr(ord(c) - 0xE0000) for c in texto if 0xE0020 <= ord(c) <= 0xE007E)


MINIMO_SUBSTANCIAL = 4  # letras/números: abaixo disso é fragmento (letra solta, glifo sem texto), ruído de leitura


def substancial(texto: str) -> bool:
    """Conteúdo de verdade: ao menos MINIMO_SUBSTANCIAL letras/números e uma palavra de 3 letras. Letras soltas
    ("i l l i"), números de eixo e glifos sem texto ("(cid:12)") são ruído; um comando para IA sempre tem palavras."""
    limpo = re.sub(r"\(cid:\d+\)", "", texto)
    return sum(ch.isalnum() for ch in limpo) >= MINIMO_SUBSTANCIAL and re.search(r"[^\W\d_]{3,}", limpo) is not None


def ocultos_relevantes(trechos: list[Trecho]) -> list[Trecho]:
    """Texto oculto que conta como risco: tem conteúdo de verdade e não é camada de OCR nem comentário."""
    return [t for t in trechos if t.motivo and t.motivo not in ("comentário do Word", OCR) and substancial(t.texto)]


def texto_oculto(trechos: list[Trecho]) -> Achado:
    ev = [f"{_onde(t)} — {t.motivo}: \"{' '.join(t.texto.split())[:200]}\"" for t in ocultos_relevantes(trechos)]
    if ev:
        return Achado("T1", "A", RISCO, "Texto oculto no documento", ev)
    fragmentos = [t for t in trechos if t.motivo and t.motivo not in ("comentário do Word", OCR) and t.texto.strip()]
    ocr = sum(1 for t in trechos if t.motivo == OCR and t.texto.strip())
    info = ([f"{len(fragmentos)} fragmento(s) sem palavras (letras soltas, números, glifos) com formatação oculta "
                  "(provável ruído de leitura)"]
            if fragmentos else []) + ([f"camada de OCR em {ocr} trecho(s): página digitalizada com texto pesquisável "
                                       "(conferida pela busca de comandos para IA)"] if ocr else [])
    return Achado("T1", "A", REVISAR if info else OK, "Texto oculto no documento", info)


def invisiveis(texto: str) -> Achado:
    contagem: dict[str, int] = {}
    for ch in texto:
        if ch in INVISIVEIS:
            contagem[INVISIVEIS[ch]] = contagem.get(INVISIVEIS[ch], 0) + 1
        elif 0xE0000 <= ord(ch) <= 0xE007F:
            contagem["caractere 'tag' Unicode (usado para esconder instruções)"] = contagem.get(
                "caractere 'tag' Unicode (usado para esconder instruções)", 0) + 1
        elif unicodedata.category(ch) == "Co":
            contagem["caractere de uso privado"] = contagem.get("caractere de uso privado", 0) + 1
    ev = [f"{qtd}× {nome}" for nome, qtd in sorted(contagem.items())]
    grave = any("tag" in e or "direção" in e for e in ev)
    return Achado("T2", "M", RISCO if grave else (REVISAR if ev else OK), "Caracteres invisíveis", ev)


def injecao(texto: str, trechos: list[Trecho], em_unicode: str = "") -> Achado:
    ev, vistos = [], set()
    ocultos = " ".join(t.texto for t in trechos if t.motivo)
    for padrao in INJECAO:
        for m in padrao.finditer(texto):
            linha = _linha(texto, m.start())
            if linha in vistos:
                continue
            vistos.add(linha)
            if em_unicode and m.group(0)[:30] in em_unicode:
                onde = "ESCRITO EM CARACTERES INVISÍVEIS"
            elif m.group(0)[:30] in ocultos:
                onde = "em TEXTO OCULTO"
            else:
                onde = "no texto visível"
            ev.append(f"{onde}: \"{linha}\"")
    return Achado("T3", "A", RISCO if ev else OK, "Frase dirigida a uma IA (injeção de prompt)", ev)


def numeros_cnj(texto: str) -> Achado:
    invalidos, validos = [], 0
    for m in CNJ.finditer(texto):
        if _dv_cnj_valido(*m.groups()):
            validos += 1
        else:
            invalidos.append(f"{m.group(0)} — dígito verificador não confere: este número não pode existir")
    ev = invalidos + ([f"{validos} número(s) com formato e dígito válidos — existência não verificada (consultar o tribunal)"]
                      if validos else [])
    resultado = RISCO if invalidos else (REVISAR if validos else NA)
    return Achado("C1", "A", resultado, "Números de processo (padrão CNJ)", ev)


def sumulas(texto: str) -> Achado:
    ev, total = [], 0
    for m in SUMULA.finditer(texto):
        total += 1
        vinculante, numero, tribunal = m.group(1), int(m.group(2).replace(".", "")), (m.group(3) or "").upper()
        chave = "SV" if vinculante else tribunal
        if chave in SUMULAS_MAX and numero > SUMULAS_MAX[chave]:
            nome = "Súmula Vinculante" if chave == "SV" else f"Súmula do {chave}"
            ev.append(f"{nome} {numero} — acima do maior número existente ({SUMULAS_MAX[chave]})")
    if ev:
        return Achado("C2", "A", RISCO, "Súmulas com número inexistente", ev)
    return Achado("C2", "A", REVISAR if total else NA,
                  f"{total} súmula(s) citada(s) — números plausíveis; conferir o enunciado" if total else "Nenhuma súmula citada", [])


def precedentes(texto: str) -> Achado:
    achados = sorted({" ".join(m.group(0).split()) for m in PRECEDENTE.finditer(texto)})
    return Achado("C3", "M", REVISAR if achados else NA,
                  f"{len(achados)} precedente(s) citado(s) — conferir cada um no site do tribunal (existência, relator, ementa)",
                  achados)


def injecao_semantica(achado: Achado, texto: str, detector) -> Achado:
    """Soma ao T3 as frases que o modelo local considera mensagem para uma IA e que as regras não pegaram."""
    ja = " ".join(achado.evidencias)
    novos = [f"por significado ({s.pontuacao:.2f}): \"{s.frase[:160]}\"" for s in detector.analisar(texto)
             if s.frase[:40] not in ja]
    if not novos:
        return achado
    return Achado(achado.item, achado.sev, RISCO, achado.titulo, achado.evidencias + novos)


def verificar(caminho: Path, semantico=None) -> tuple[list[Achado], dict]:
    caminho = Path(caminho)
    trechos = extrair(caminho)
    texto = "".join(t.texto for t in trechos)
    escondido = _decodificar_tags(texto)  # instrução escrita em caracteres "tag" (invisível na tela)
    t3 = injecao(texto + "\n" + escondido, trechos, escondido)
    if semantico is not None:
        t3 = injecao_semantica(t3, texto + "\n" + escondido, semantico)
    achados = [texto_oculto(trechos), invisiveis(texto), t3, numeros_cnj(texto), sumulas(texto), precedentes(texto)]
    achados += vazamento.verificar(caminho, texto)
    info = {"paginas": max((t.pagina for t in trechos), default=0), "caracteres": len(texto)}
    return achados, info
