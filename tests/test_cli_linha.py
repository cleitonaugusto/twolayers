"""linha-do-tempo: o exemplo de perícia do README tem de continuar dizendo o que diz."""

import runpy
from pathlib import Path

from twolayers.cli_linha import main

EXEMPLO = Path(__file__).resolve().parents[1] / "exemplos" / "pericia-sessoes"


def test_exemplo_word_diz_quem_foi_escondido_depois(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["gerar.py"])
    runpy.run_path(str(EXEMPLO / "gerar.py"))
    assert main([str(EXEMPLO / "manifestacao_ficticia.docx")]) == 0
    saida = capsys.readouterr().out
    assert "Proposta de acordo" in saida and "escondido DEPOIS de digitado" in saida and "sessão 3 de 3" in saida
    assert "entrou no documento JÁ escondido" in saida


def test_exemplo_pdf_mostra_o_valor_que_mudou(capsys):
    assert main([str(EXEMPLO / "peticao_duas_versoes.pdf")]) == 0
    saida = capsys.readouterr().out
    assert "2 versão(ões)" in saida and "saiu    Valor do acordo: R$ 50.000,00." in saida
    assert "entrou  Valor do acordo: R$ 80.000,00." in saida


def test_formato_nao_suportado(tmp_path):
    arq = tmp_path / "peca.odt"
    arq.write_bytes(b"x")
    assert main([str(arq)]) == 2
