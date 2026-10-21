"""Linha do tempo de um documento, para exame pericial: o que o arquivo guarda sobre COMO chegou a ser o que é.

DOCX: propriedades, sessões de edição (rsid), texto oculto com a sessão em que foi DIGITADO (rsidR) e a sessão da
última mudança de FORMATAÇÃO (rsidRPr, quando pode ter sido escondido), alterações rastreadas e comentários.
PDF: cada versão salva dentro do arquivo (rodapé estrutural 'startxref N %%EOF'; PDF linearizado; dados acrescentados
depois do fim), com os metadados de cada versão e o que mudou de uma para outra.

Limites: rsid ordena sessões, não dá hora nem pessoa; rsidRPr é a ÚLTIMA mudança de formatação. Um PDF regravado do
zero não guarda versões anteriores.
"""

import difflib
import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from . import formatacao, peca

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"dc": "http://purl.org/dc/elements/1.1/",
      "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
      "dcterms": "http://purl.org/dc/terms/",
      "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}

# ------------------------------------------------------------------ DOCX


def _texto(raiz, caminho: str) -> str | None:
    el = raiz.find(caminho, NS) if raiz is not None else None
    return el.text if el is not None and el.text else None


def docx(caminho: Path) -> dict:
    with zipfile.ZipFile(caminho) as z:
        nomes = set(z.namelist())
        xml = lambda n: ElementTree.fromstring(z.read(n)) if n in nomes else None  # noqa: E731
        core, app, settings = xml("docProps/core.xml"), xml("docProps/app.xml"), xml("word/settings.xml")
        props = {
            "autor": _texto(core, "dc:creator"), "modificado_por": _texto(core, "cp:lastModifiedBy"),
            "criado_em": _texto(core, "dcterms:created"), "modificado_em": _texto(core, "dcterms:modified"),
            "revisao": _texto(core, "cp:revision"), "modelo": _texto(app, "ep:Template"),
            "tempo_total_edicao_min": _texto(app, "ep:TotalTime"), "aplicativo": _texto(app, "ep:Application"),
            "versao_aplicativo": _texto(app, "ep:AppVersion"), "empresa": _texto(app, "ep:Company"),
        }
        # sessões de edição: o Word grava um rsid por sessão, em ordem, em settings.xml
        sessoes = [el.get(f"{W}val") for el in settings.iter(f"{W}rsid")] if settings is not None else []
        if settings is not None and (raiz := settings.find(f"{W}rsids/{W}rsidRoot")) is not None:
            props["sessao_raiz"] = raiz.get(f"{W}val")
        ordem = {r: i + 1 for i, r in enumerate(sessoes)}
        # mesma regra de "oculto" do verificador do kit (formatação efetiva + contraste com o fundo)
        estilos = formatacao.Estilos(xml("word/styles.xml"))
        papel = formatacao.papel(xml("word/document.xml"))

        alteracoes, ocultos, comentarios = [], [], []
        partes = sorted(n for n in nomes if re.match(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$", n))
        for parte in partes:
            raiz = xml(parte)
            for tag, tipo in (("ins", "inserção"), ("del", "exclusão"), ("moveFrom", "movido de"), ("moveTo", "movido para")):
                for el in raiz.iter(f"{W}{tag}"):
                    texto = "".join(t.text or "" for t in el.iter() if t.tag in (f"{W}t", f"{W}delText"))
                    if texto.strip():
                        alteracoes.append({"tipo": tipo, "autor": el.get(f"{W}author"), "data": el.get(f"{W}date"),
                                           "texto": " ".join(texto.split())[:300], "parte": parte})
            for par, runs in formatacao.trechos(raiz, estilos, papel):
                rsid_par = par.get(f"{W}rsidR")
                for run, texto, _, motivo in runs:
                    if not texto.strip() or not motivo:
                        continue
                    rsid = run.get(f"{W}rsidR") or rsid_par
                    # rsidRPr = sessão da última mudança de FORMATAÇÃO do trecho (é quando ele pode ter sido escondido)
                    rsid_fmt = run.get(f"{W}rsidRPr") or rsid
                    ocultos.append({"texto": " ".join(texto.split())[:300], "motivo": motivo, "parte": parte,
                                    "sessao": rsid, "sessao_n": ordem.get(rsid), "sessoes_total": len(sessoes),
                                    "sessao_raiz": rsid is not None and rsid == props.get("sessao_raiz"),
                                    "sessao_ocultacao": rsid_fmt, "sessao_ocultacao_n": ordem.get(rsid_fmt),
                                    "ocultacao_registrada": run.get(f"{W}rsidRPr") is not None})
        if (com := xml("word/comments.xml")) is not None:
            for el in com.iter(f"{W}comment"):
                comentarios.append({"autor": el.get(f"{W}author"), "data": el.get(f"{W}date"),
                                    "texto": " ".join("".join(t.text or "" for t in el.iter(f"{W}t")).split())[:300]})
    return {"formato": "docx", "propriedades": props, "sessoes_de_edicao": len(sessoes),
            "texto_oculto_por_sessao": ocultos, "alteracoes_rastreadas": alteracoes, "comentarios": comentarios}

# ------------------------------------------------------------------ PDF


def _data_pdf(valor: bytes | None) -> str | None:
    m = re.match(rb"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Z+\-])?(\d{2})?'?(\d{2})?", valor or b"")
    if not m:
        return None
    p = [g.decode() if g else None for g in m.groups()]
    data = f"{p[0]}-{p[1] or '01'}-{p[2] or '01'}T{p[3] or '00'}:{p[4] or '00'}:{p[5] or '00'}"
    if p[6] == "Z":
        return data + "Z"
    return data + (f"{p[6]}{p[7]}:{p[8] or '00'}" if p[6] and p[7] else "")


def _info_bruta(dados: bytes) -> dict:
    """Metadados do último dicionário /Info visível nesta revisão (leitura direta, sem depender do parser)."""
    info = {}
    for campo in ("Producer", "Creator", "Author", "CreationDate", "ModDate"):
        achados = re.findall(rb"/" + campo.encode() + rb"\s*\(((?:\\.|[^\\)])*)\)", dados)
        if achados:
            bruto = achados[-1]
            info[campo] = _data_pdf(bruto) if campo.endswith("Date") else bruto.decode("latin-1")
    return info


FIM_DE_VERSAO = re.compile(rb"startxref\s+(\d+)\s*%%EOF[ \t]*(?:\r\n|\r|\n)?")


def pdf(caminho: Path, pasta: Path) -> dict:
    """Versões salvas dentro do PDF. Cada gravação termina em 'startxref <n> %%EOF' (um %%EOF solto no conteúdo não
    conta). PDF linearizado ("otimizado para web") tem um rodapé extra na primeira gravação, que não é outra versão.
    Bytes depois do último rodapé são registrados à parte: não são uma versão, são dados acrescentados ao arquivo."""
    dados = caminho.read_bytes()
    fins = [m.end() for m in FIM_DE_VERSAO.finditer(dados)]
    linearizado = re.search(rb"/Linearized\s", dados[:2048]) is not None
    if linearizado and len(fins) > 1:
        fins = fins[1:]  # o primeiro rodapé fecha só a tabela da primeira página
    apos = dados[fins[-1]:] if fins else b""
    dados_apos_fim = None
    if apos.strip():
        dados_apos_fim = {"bytes": len(apos), "sha256": hashlib.sha256(apos).hexdigest(),
                          "inicio": apos.strip()[:80].decode("latin-1")}
    revisoes = []
    for i, fim in enumerate(fins, 1):
        trecho = dados[:fim]
        arq = pasta / f"{caminho.stem}.r{i}.pdf"
        arq.write_bytes(trecho)
        try:
            texto = "".join(t.texto for t in peca.extrair_pdf(arq))
        except Exception as e:  # versão intermediária pode não abrir sozinha
            texto, erro = "", str(e)
        else:
            erro = None
        revisoes.append({"n": i, "ate_byte": fim, "sha256": hashlib.sha256(trecho).hexdigest(),
                         "info": _info_bruta(trecho), "arquivo": arq.name, "erro": erro, "_texto": texto})
    for anterior, atual in zip(revisoes, revisoes[1:]):
        atual["mudou_em_relacao_a_anterior"] = diferenca(anterior["_texto"], atual["_texto"])
    for r in revisoes:
        r.pop("_texto")
    return {"formato": "pdf", "linearizado": linearizado, "revisoes": revisoes, "dados_apos_o_fim": dados_apos_fim}


def revisoes_pdf(caminho: Path, pasta: Path) -> list[dict]:
    return pdf(caminho, pasta)["revisoes"]


def diferenca(antes: str, depois: str, limite: int = 60) -> list[str]:
    a = [" ".join(l.split()) for l in antes.splitlines() if l.strip()]
    b = [" ".join(l.split()) for l in depois.splitlines() if l.strip()]
    linhas = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return linhas[:limite] + ([f"... mais {len(linhas) - limite} linhas"] if len(linhas) > limite else [])
