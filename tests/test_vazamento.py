"""Testes do vazamento por documento (V1–V5) com DOCX e PDF fictícios montados na hora."""

import pytest

from twolayers.documentos import atualizar_pdf, escrever_docx, escrever_pdf
from twolayers.peca import verificar
from twolayers.achados import NA, OK, REVISAR, RISCO

pytest.importorskip("pdfminer")

PRETO = (0, 0, 0)
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
CORPO = [("Requer a juntada dos documentos anexos.", "")]
LINHAS = [("Requer a juntada dos documentos anexos.", 12, PRETO, 72, 700)]


def _v(caminho):
    return {a.item: a for a in verificar(caminho)[0] if a.item.startswith("V")}


def _ev(achado):
    return " ".join(achado.evidencias)


def test_docx_limpo(tmp_path):
    v = _v(escrever_docx(tmp_path / "limpa.docx", CORPO))
    assert all(v[i].resultado == OK for i in ("V1", "V2", "V3", "V5")) and v["V4"].resultado == NA


def test_docx_alteracao_rastreada_mostra_texto_apagado(tmp_path):
    xml = (f'<w:p><w:del w:author="Estagiario Ficticio"><w:r><w:delText>Proposta de acordo: aceitamos R$ 50.000,00'
           '</w:delText></w:r></w:del><w:ins w:author="Socio Ficticio"><w:r><w:t>Requer o prosseguimento.</w:t>'
           '</w:r></w:ins></w:p>')
    v = _v(escrever_docx(tmp_path / "rastreada.docx", CORPO, xml))
    assert v["V1"].resultado == RISCO
    assert "Proposta de acordo" in _ev(v["V1"]) and "Estagiario Ficticio" in _ev(v["V1"])


def test_docx_so_insercao_pendente_e_revisar(tmp_path):
    xml = '<w:p><w:ins w:author="Socio Ficticio"><w:r><w:t>Requer o prosseguimento.</w:t></w:r></w:ins></w:p>'
    assert _v(escrever_docx(tmp_path / "ins.docx", CORPO, xml))["V1"].resultado == REVISAR


def test_docx_comentario_metadados_e_macro(tmp_path):
    partes = {
        "word/comments.xml": f'<w:comments {NS}><w:comment w:id="0" w:author="Socio Ficticio"><w:p><w:r>'
                             '<w:t>Cliente admitiu a divida, nao mencionar</w:t></w:r></w:p></w:comment></w:comments>',
        "docProps/core.xml": '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
                             'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Fulano Ficticio'
                             '</dc:creator></cp:coreProperties>',
        "word/_rels/settings.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                                        'relationships"><Relationship Id="rId1" Type="x/attachedTemplate" '
                                        'Target="file:///\\\\servidor\\modelos\\Outro Escritorio\\contestacao.dotx" '
                                        'TargetMode="External"/></Relationships>',
        "word/vbaProject.bin": b"\x00macro ficticia",
    }
    v = _v(escrever_docx(tmp_path / "vaza.docx", CORPO, partes=partes))
    assert v["V2"].resultado == RISCO and "nao mencionar" in _ev(v["V2"])
    assert v["V3"].resultado == RISCO and "Outro Escritorio" in _ev(v["V3"]) and "Fulano Ficticio" in _ev(v["V3"])
    assert v["V5"].resultado == RISCO and "vbaProject.bin" in _ev(v["V5"])


def test_docx_so_autor_e_revisar(tmp_path):
    partes = {"docProps/core.xml": '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                                   'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                   '<dc:creator>Fulano Ficticio</dc:creator></cp:coreProperties>'}
    assert _v(escrever_docx(tmp_path / "autor.docx", CORPO, partes=partes))["V3"].resultado == REVISAR


def test_pdf_limpo(tmp_path):
    v = _v(escrever_pdf(tmp_path / "limpa.pdf", LINHAS))
    assert all(v[i].resultado == OK for i in ("V1", "V2", "V3", "V4", "V5"))


def test_pdf_comentario_metadados_e_javascript(tmp_path):
    pdf = escrever_pdf(tmp_path / "vaza.pdf", LINHAS,
                       info={"Author": "Fulano Ficticio", "Title": "C:\\Users\\fulano\\Clientes\\Ficticia\\peticao.docx",
                             "Producer": "gerador ficticio"},
                       comentarios=[("Socio Ficticio", "Conferir com o cliente antes: prova fraca")],
                       javascript="void 0")
    v = _v(pdf)
    assert v["V2"].resultado == RISCO and "prova fraca" in _ev(v["V2"])
    assert v["V3"].resultado == RISCO and "Clientes" in _ev(v["V3"]) and "gerador" not in _ev(v["V3"])
    assert v["V5"].resultado == RISCO and "JavaScript" in _ev(v["V5"])


def test_pdf_versao_anterior_recuperavel(tmp_path):
    pdf = escrever_pdf(tmp_path / "versoes.pdf", LINHAS + [("Valor minimo aceito no acordo: R$ 30.000,00", 12, PRETO, 72, 680)])
    atualizar_pdf(pdf, LINHAS)
    v = _v(pdf)
    assert v["V4"].resultado == RISCO and "Valor minimo aceito" in _ev(v["V4"])
    assert "Valor minimo" not in " ".join(e for a in verificar(pdf)[0] if a.item == "T1" for e in a.evidencias)


def test_pdf_salvo_de_novo_sem_mudanca_nao_e_risco(tmp_path):
    pdf = escrever_pdf(tmp_path / "assinado.pdf", LINHAS)
    atualizar_pdf(pdf, LINHAS)
    v = _v(pdf)
    assert v["V4"].resultado == OK and "nenhum texto removido" in _ev(v["V4"])


def test_docx_modelo_remoto_e_docm(tmp_path):
    rel = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId9" '
           'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" '
           'Target="http://exemplo.invalid/modelos/malicioso.dotx" TargetMode="External"/></Relationships>')
    v = _v(escrever_docx(tmp_path / "remoto.docm", CORPO, partes={"word/_rels/settings.xml.rels": rel}))
    assert v["V5"].resultado == RISCO and "modelo remoto" in _ev(v["V5"])


def test_pdf_com_baloes_do_word_impressos(tmp_path):
    pdf = escrever_pdf(tmp_path / "marcacao.pdf", LINHAS + [
        ("Comentado [CA1]: conferir se o cliente pagou mesmo", 8, PRETO, 450, 650),
        ("Excluído: proposta de R$ 40.000,00", 8, PRETO, 450, 620),
    ])
    v = _v(pdf)
    assert v["V2"].resultado == RISCO and "conferir se o cliente" in _ev(v["V2"])
    assert v["V1"].resultado == RISCO and "proposta de R$" in _ev(v["V1"])
