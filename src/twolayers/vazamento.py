"""Vazamento por documento: o que o arquivo leva junto além do texto que aparece na tela.

Tudo roda na máquina, sem rede. O que é verificado:
  V1  alterações rastreadas do Word (o texto apagado continua no arquivo)
  V2  comentários do Word e anotações de PDF
  V3  metadados: autor, empresa, modelo; caminhos de arquivo ou de rede internos
  V4  versões anteriores recuperáveis em PDF salvo por atualização incremental
  V5  conteúdo ativo ou embutido: JavaScript e ações em PDF, macros, arquivos anexados, vínculos externos
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from .achados import NA, OK, REVISAR, RISCO, Achado

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CAMINHO = re.compile(r"(?i)(?:[a-z]:\\[^\"<>|\r\n]{2,}|\\\\[\w.$-]+\\[^\"<>|\r\n]+|file:/{2,3}[^\"<>\r\n]+"
                     r"|/(?:home|Users)/[^\"<>\s]+)")
CAMPOS_DOCX = {"creator": "autor", "lastModifiedBy": "modificado por", "title": "título", "subject": "assunto",
               "keywords": "palavras-chave", "description": "descrição", "category": "categoria",
               "Company": "empresa", "Manager": "gerente", "Template": "modelo"}
CAMPOS_PDF = {"Author": "autor", "Title": "título", "Subject": "assunto", "Keywords": "palavras-chave"}
CAMPOS_TECNICOS = {"Creator", "Producer", "CreationDate", "ModDate", "Trapped", "SourceModified", "HyperlinksChanged",
                   "LinksUpToDate", "ScaleCrop", "ShareDoc", "Build", "AppVersion", "DocSecurity"}
WORD = (".docx", ".docm", ".dotx", ".dotm")
# balões que o Word imprime quando o PDF é exportado com a marcação visível
BALAO_COMENTARIO = re.compile(r"(?m)\b(?:Comment|Comentário|Comentado|Comentou)\s*\[[A-Za-z]{1,6}\d+\]\s*:.*")
BALAO_ALTERACAO = re.compile(r"(?m)^\s*(?:Deleted|Excluído|Excluído\(s\)|Inserted|Inserido)\s*:.*")
ANOTACOES_SEM_COMENTARIO = {"Link", "Widget", "Popup", "PrinterMark", "TrapNet", "Watermark"}


def _curto(texto: str, n: int = 160) -> str:
    return " ".join(str(texto).split())[:n]


def _caminhos(texto: str) -> list[str]:
    return sorted({m.group(0).rstrip(".,;)") for m in CAMINHO.finditer(texto)})


# ------------------------------------------------------------------ DOCX

def docx(caminho: Path) -> list[Achado]:
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        ler = lambda n: z.read(n).decode("utf-8", "replace") if n in nomes else ""  # noqa: E731
        partes = [n for n in nomes if re.match(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$", n)]

        apagados, inseridos, autores = [], 0, set()
        for parte in partes:
            raiz = ElementTree.fromstring(z.read(parte))
            for tag in ("del", "moveFrom"):
                for el in raiz.iter(f"{W}{tag}"):
                    autores.add(el.get(f"{W}author") or "?")
                    texto = "".join(t.text or "" for t in el.iter() if t.tag in (f"{W}delText", f"{W}t"))
                    if texto.strip():
                        apagados.append(texto)
            for el in raiz.iter(f"{W}ins"):
                autores.add(el.get(f"{W}author") or "?")
                inseridos += 1
        ev = [f"texto apagado que continua no arquivo: \"{_curto(t)}\"" for t in apagados[:10]]
        if inseridos:
            ev.append(f"{inseridos} inserção(ões) ainda não aceita(s)")
        if autores:
            ev.append("autores das alterações: " + ", ".join(sorted(autores)))
        v1 = Achado("V1", "A", RISCO if apagados else (REVISAR if inseridos else OK),
                    "Alterações rastreadas (controle de alterações)", ev)

        comentarios = []
        if "word/comments.xml" in nomes:
            raiz = ElementTree.fromstring(z.read("word/comments.xml"))
            for c in raiz.iter(f"{W}comment"):
                texto = "".join(t.text or "" for t in c.iter(f"{W}t"))
                comentarios.append(f"{c.get(f'{W}author') or '?'}: \"{_curto(texto)}\"")
        v2 = Achado("V2", "M", RISCO if comentarios else OK, "Comentários internos no documento", comentarios)

        meta, caminhos = [], []
        for parte in ("docProps/core.xml", "docProps/app.xml"):
            if parte in nomes:
                for el in ElementTree.fromstring(z.read(parte)).iter():
                    campo = el.tag.split("}")[-1]
                    if campo in CAMPOS_DOCX and (el.text or "").strip():
                        meta.append(f"{CAMPOS_DOCX[campo]}: {_curto(el.text, 120)}")
        if "docProps/custom.xml" in nomes:
            for el in ElementTree.fromstring(z.read("docProps/custom.xml")):
                valor = "".join(x.text or "" for x in el.iter())
                meta.append(f"propriedade personalizada {el.get('name')}: {_curto(valor, 120)}")
        for n in nomes:
            if n.startswith(("docProps/", "word/")) and n.endswith((".xml", ".rels")):
                caminhos += _caminhos(ler(n))
        v3 = _metadados(meta, caminhos)

        externos, remotos = set(), set()
        for n in nomes:
            if not n.endswith(".rels"):
                continue
            for rel in ElementTree.fromstring(z.read(n)):
                alvo, tipo = rel.get("Target") or "", rel.get("Type") or ""
                if rel.get("TargetMode") != "External":
                    continue
                if tipo.endswith("/attachedTemplate") and alvo.lower().startswith(("http://", "https://", "\\\\")):
                    remotos.add(alvo)  # o Word baixa o modelo ao abrir: técnica conhecida de ataque
                elif not alvo.lower().startswith(("http://", "https://", "mailto:")):
                    externos.add(alvo)
        macros = [n for n in nomes if n.lower().endswith("vbaproject.bin")]
        embutidos = [n for n in nomes if n.startswith("word/embeddings/")]
        if "/aFChunk" in ler("word/_rels/document.xml.rels"):
            embutidos.append("conteúdo importado de outro arquivo (altChunk)")
        ev = [f"macro: {n}" for n in macros] + [f"modelo remoto baixado ao abrir o arquivo: {t}" for t in sorted(remotos)] \
            + [f"arquivo embutido: {n}" for n in embutidos] + [f"vínculo externo: {t}" for t in sorted(externos)]
        v5 = Achado("V5", "A", RISCO if macros or remotos else (REVISAR if ev else OK), "Conteúdo ativo ou embutido", ev)
    v4 = Achado("V4", "A", NA, "Versões anteriores dentro do arquivo", ["só se aplica a PDF"])
    return [v1, v2, v3, v4, v5]


def _metadados(meta: list[str], caminhos: list[str]) -> Achado:
    ev = [f"caminho interno: {c}" for c in sorted(set(caminhos))] + list(dict.fromkeys(meta))
    resultado = RISCO if caminhos else (REVISAR if meta else OK)
    return Achado("V3", "M", resultado, "Metadados (autor, empresa, modelo, caminhos)", ev)


# ------------------------------------------------------------------ PDF

def _texto_pdf(valor) -> str:
    from pdfminer.pdftypes import resolve1
    from pdfminer.utils import decode_text
    valor = resolve1(valor)
    if isinstance(valor, bytes):
        return decode_text(valor)
    return str(getattr(valor, "name", valor) or "")


def _nome(valor) -> str:
    from pdfminer.pdftypes import resolve1
    valor = resolve1(valor)
    return str(getattr(valor, "name", valor) or "")


def _objetos(doc):
    from pdfminer.pdftypes import PDFStream
    vistos = set()
    for xref in doc.xrefs:
        for objid in xref.get_objids():
            if objid in vistos:
                continue
            vistos.add(objid)
            try:
                obj = doc.getobj(objid)
            except Exception:  # objeto corrompido ou inexistente: ignora
                continue
            pilha = [obj.attrs if isinstance(obj, PDFStream) else obj]
            while pilha:  # dicionários aninhados também (ex.: /OpenAction escrito direto no catálogo)
                d = pilha.pop()
                if isinstance(d, dict):
                    yield d
                    pilha += [x for x in d.values() if isinstance(x, (dict, list))]
                elif isinstance(d, list):
                    pilha += [x for x in d if isinstance(x, (dict, list))]


def _linhas(texto: str) -> list[str]:
    return [" ".join(l.split()) for l in texto.splitlines() if len(" ".join(l.split())) >= 4]


def pdf(caminho: Path, texto_final: str | None = None) -> list[Achado]:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser
    from .peca import extrair_pdf

    dados = caminho.read_bytes()
    doc = PDFDocument(PDFParser(BytesIO(dados)))
    comentarios, ativos, embutidos = [], [], []
    for d in _objetos(doc):
        tipo, sub = _nome(d.get("Type")), _nome(d.get("Subtype"))
        if (tipo == "Annot" or "Contents" in d and "Rect" in d) and sub not in ANOTACOES_SEM_COMENTARIO:
            texto = _texto_pdf(d.get("Contents")) if "Contents" in d else ""
            autor = _texto_pdf(d.get("T")) if "T" in d else "?"
            if texto.strip():
                comentarios.append(f"{sub or 'anotação'} de {autor}: \"{_curto(texto)}\"")
            if sub == "FileAttachment":
                embutidos.append("anexo em anotação")
        acao = _nome(d.get("S"))
        if "JS" in d or acao == "JavaScript":
            ativos.append("JavaScript: \"" + _curto(_texto_pdf(d.get("JS")), 80) + "\"")
        if acao in ("Launch", "ImportData", "SubmitForm"):
            ativos.append(f"ação {acao} (abre programa, importa ou envia dados)")
        if tipo == "EmbeddedFile" or "EmbeddedFiles" in d:
            embutidos.append("arquivo embutido" + (f": {_texto_pdf(d.get('F'))}" if "F" in d else ""))
        if "RichMedia" in (tipo, sub):
            embutidos.append("mídia embutida (RichMedia)")

    if texto_final is None:
        texto_final = "".join(t.texto for t in extrair_pdf(BytesIO(dados)))
    comentarios += [f"comentário do Word impresso na página: \"{_curto(m.group(0))}\""
                    for m in BALAO_COMENTARIO.finditer(texto_final)]
    baloes = [f"alteração do Word impressa na página: \"{_curto(m.group(0))}\""
              for m in BALAO_ALTERACAO.finditer(texto_final)]
    v2 = Achado("V2", "M", RISCO if comentarios else OK, "Comentários internos no documento", comentarios)

    meta, caminhos = [], []
    for info in doc.info:
        for campo, valor in info.items():
            texto = _texto_pdf(valor)
            if not texto.strip():
                continue
            caminhos += _caminhos(texto)
            if campo in CAMPOS_PDF:
                meta.append(f"{CAMPOS_PDF[campo]}: {_curto(texto, 120)}")
            elif campo.startswith("2.16.76.1."):
                meta.append(f"campo de certificado ICP-Brasil {campo}: {_curto(texto, 120)}")
            elif campo not in CAMPOS_TECNICOS:
                meta.append(f"campo {campo}: {_curto(texto, 120)}")
    v3 = _metadados(meta, caminhos)

    # versões anteriores: cada %%EOF antes do último fecha uma versão salva que continua dentro do arquivo
    fins = [m.end() for m in re.finditer(rb"%%EOF", dados)][:-1]
    removidas, lidas = [], 0
    if fins:
        atual = set(_linhas(texto_final))
        for fim in fins:
            try:
                anteriores = _linhas("".join(t.texto for t in extrair_pdf(BytesIO(dados[:fim]))))
            except Exception:  # versão parcial (ex.: PDF linearizado) que não abre sozinha
                continue
            lidas += 1
            removidas += [l for l in anteriores if l not in atual and l not in removidas]
    assinado = b"/ByteRange" in dados
    if removidas:
        v4 = Achado("V4", "A", RISCO, "Versões anteriores dentro do arquivo",
                    [f"texto de versão anterior que não está na versão final: \"{_curto(l)}\"" for l in removidas[:10]])
    elif fins:
        v4 = Achado("V4", "A", OK, "Versões anteriores dentro do arquivo",
                    [f"{len(fins)} atualização(ões) incremental(is), {lidas} legível(is); nenhum texto removido entre "
                     "elas" + (" (comum em PDF com assinatura digital)" if assinado else "")])
    else:
        v4 = Achado("V4", "A", OK, "Versões anteriores dentro do arquivo", [])

    ev = ativos + embutidos
    v5 = Achado("V5", "A", RISCO if ativos else (REVISAR if embutidos else OK), "Conteúdo ativo ou embutido", ev)
    v1 = Achado("V1", "A", RISCO if baloes else OK, "Alterações rastreadas (controle de alterações)", baloes)
    return [v1, v2, v3, v4, v5]


def verificar(caminho: Path, texto: str | None = None) -> list[Achado]:
    """texto: o texto já extraído do PDF, para não ler o arquivo duas vezes."""
    sufixo = caminho.suffix.lower()
    if sufixo in WORD:
        return docx(caminho)
    if sufixo == ".pdf":
        return pdf(caminho, texto)
    return []
