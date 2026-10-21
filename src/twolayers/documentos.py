"""Escrita mínima de PDF e DOCX, sem dependências, para montar documentos fictícios (exemplos, testes e validação)."""

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _pdf_str(texto: str) -> bytes:
    t = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return b"(" + t.encode("cp1252", errors="replace") + b")"


def _conteudo(linhas) -> bytes:
    ops = []
    for item in linhas:
        if item[0] == "RET":
            _, x, y, w, h, cor = item
            ops.append(f"{cor[0]} {cor[1]} {cor[2]} rg {x} {y} {w} {h} re f")
            continue
        if item[0] == "MARCA":  # marca-texto de verdade: retângulo com 35% de opacidade (o texto continua visível)
            _, x, y, w, h, cor = item
            ops.append(f"q /Transp gs {cor[0]} {cor[1]} {cor[2]} rg {x} {y} {w} {h} re f Q")
            continue
        if item[0] == "IMG":  # imagem (2×2 cinza) esticada no retângulo: simula página digitalizada ou foto
            _, x, y, w, h = item
            ops.append(f"q {w} 0 0 {h} {x} {y} cm BI /W 2 /H 2 /CS /G /BPC 8 ID @@@@ EI Q")
            continue
        texto, tam, cor, x, y, *modo = item
        t = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        tr = f" {modo[0]} Tr" if modo else ""
        ops.append(f"BT /F1 {tam} Tf{tr} {cor[0]} {cor[1]} {cor[2]} rg {x} {y} Td ({t}) Tj ET")
    return "\n".join(ops).encode("cp1252", errors="replace")


def escrever_pdf(caminho: Path, linhas, info=None, comentarios=(), javascript=None, cropbox=None) -> Path:
    """linhas, desenhadas na ordem: (texto, tamanho_pt, cor_rgb, x, y[, modo_Tr]), ("RET", x, y, larg, alt, cor_rgb),
    um retângulo preenchido opaco, ("MARCA", x, y, larg, alt, cor_rgb), um retângulo 35% opaco (marca-texto), ou
    ("IMG", x, y, larg, alt), uma imagem. Fonte Helvetica com WinAnsi (acentos do português).
    info: metadados {campo: valor}; comentarios: (autor, texto) como anotações; javascript: ação ao abrir."""
    conteudo = _conteudo(linhas)
    catalogo = b"<< /Type /Catalog /Pages 2 0 R >>"
    if javascript is not None:
        catalogo = b"<< /Type /Catalog /Pages 2 0 R /OpenAction << /S /JavaScript /JS " + _pdf_str(javascript) + b" >> >>"
    anotacoes = b"".join(b" %d 0 R" % (6 + i) for i in range(len(comentarios)))
    corte = (b" /CropBox [%s]" % " ".join(str(v) for v in cropbox).encode()) if cropbox else b""
    pagina = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]" + corte + b" /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> /ExtGState << /Transp << /ca 0.35 >> >> >>"
    pagina += (b" /Annots [" + anotacoes[1:] + b"] >>") if comentarios else b" >>"
    objetos = [
        catalogo,
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        pagina,
        b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for k, (autor, texto) in enumerate(comentarios):
        objetos.append(b"<< /Type /Annot /Subtype /Text /Rect [540 %d 560 %d] /T " % (700 - 30 * k, 720 - 30 * k)
                       + _pdf_str(autor) + b" /Contents " + _pdf_str(texto) + b" >>")
    extra_trailer = b""
    if info:
        objetos.append(b"<< " + b" ".join(b"/" + k.encode() + b" " + _pdf_str(v) for k, v in info.items()) + b" >>")
        extra_trailer = b" /Info %d 0 R" % len(objetos)
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    saida += b"".join(b"%010d 00000 n \n" % p for p in posicoes)
    saida += b"trailer\n<< /Size %d /Root 1 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, extra_trailer, xref)
    caminho.write_bytes(bytes(saida))
    return caminho


def atualizar_pdf(caminho: Path, linhas) -> Path:
    """Salva de novo por atualização incremental, trocando o conteúdo da página: a versão antiga continua no arquivo."""
    dados = caminho.read_bytes()
    conteudo = _conteudo(linhas)
    anterior = int(re.findall(rb"startxref\s+(\d+)", dados)[-1])
    trailer = re.findall(rb"trailer\s*<<(.*?)>>\s*startxref", dados, re.S)[-1]
    tamanho = re.search(rb"/Size (\d+)", trailer).group(1)
    info = re.search(rb"/Info \d+ 0 R", trailer)
    pos = len(dados)
    obj = b"4 0 obj\n<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream\nendobj\n"
    xref = pos + len(obj)
    caminho.write_bytes(dados + obj + b"xref\n0 1\n0000000000 65535 f \n4 1\n%010d 00000 n \n" % pos
                        + b"trailer\n<< /Size %s /Root 1 0 R /Prev %d%s >>\nstartxref\n%d\n%%%%EOF\n"
                        % (tamanho, anterior, (b" " + info.group(0)) if info else b"", xref))
    return caminho


def escrever_docx(caminho: Path, runs, xml_extra: str = "", partes=None) -> Path:
    """runs: (texto, propriedades_xml_do_run). Um parágrafo por run.
    xml_extra: parágrafos em XML cru no fim do corpo (ex.: alteração rastreada); partes: {nome no zip: conteúdo}."""
    corpo = "".join(f'<w:p><w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(texto)}</w:t></w:r></w:p>'
                    for texto, props in runs) + xml_extra
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{corpo}</w:body></w:document>")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
        for nome, conteudo in (partes or {}).items():
            z.writestr(nome, conteudo)
    return caminho
