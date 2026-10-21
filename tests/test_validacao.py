"""Validação do método de perícia de documentos: nenhuma falha fora das lacunas conhecidas e nenhuma afirmação abaixo
da linha de base registrada (validacao/resultados/kit-0.18.0). Se uma mudança piorar uma taxa, este teste falha.
Sem os arquivos reais (AUDITAR_CORPUS_REAL), os casos reais são pulados e o resto continua valendo."""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "validacao"))
import medir  # noqa: E402


def test_sem_regressao():
    r = medir.rodar()
    imprevistas = [f for f in r["falhas"] if not f["lacuna_conhecida"]]
    assert not imprevistas, imprevistas
    base = json.loads((RAIZ / "validacao" / "resultados" / "kit-0.18.0" / "resultado.json").read_text())["metricas"]
    for nome, m in base.items():
        if nome in r["metricas"]:  # afirmação medida só com arquivos reais pode faltar sem AUDITAR_CORPUS_REAL
            assert r["metricas"][nome]["taxa_de_acerto"] >= m["taxa_de_acerto"], (nome, r["metricas"][nome], m)
