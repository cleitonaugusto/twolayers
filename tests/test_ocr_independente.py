"""Regra de busca do verificador independente (OCR): o trecho acusado só conta como visível se as palavras aparecem
na mesma ordem. A regra só por semelhança aceitou "55 system summary" (página + título) como a legenda escondida."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validacao" / "segundo-avaliador"))
import ocr_independente as o  # noqa: E402


def test_palavras_em_outra_ordem_nao_contam():
    lido = "JSC-63743 Page 55 System Summary Table 1 summarizes all of the system leads data"
    assert o.encontra("Table 1. System Summary.", lido, estrito=True) is False
    assert o.encontra("Table 1. System Summary.", lido, estrito=False) is True  # o falso acerto da regra antiga


def test_ocr_imperfeito_ainda_acha_o_texto_visivel():
    assert o.encontra("Total Internal Volume (m3)", "Total Internal Volume (m?) 350.0", estrito=True)
    assert o.encontra("Respectfully submitted today", "respect fully submitted today", estrito=True)
    assert o.encontra("Table 1 summarizes all of the system", "Table l summarizes all of the systen", estrito=True)
