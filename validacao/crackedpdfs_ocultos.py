"""Etapa 1 da avaliação no CrackedPDFs: extrai, de cada PDF do split de teste, o texto que o kit considera oculto.

    PYTHONPATH=~/kit-auditoria-mcp/src python3 -I validacao/crackedpdfs_ocultos.py <pasta-teste> <saida.json>
"""
import json
import logging
import sys
from multiprocessing import get_context
from pathlib import Path


def _um(caminho: str):
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    from twolayers import peca as kp
    try:
        trechos = kp.ocultos_relevantes(kp.extrair_pdf(Path(caminho)))
        return Path(caminho).stem, " \n".join(" ".join(t.texto.split()) for t in trechos)[:4000]
    except Exception:  # noqa: BLE001  (arquivo que não abre: fica sem texto oculto)
        return Path(caminho).stem, None


if __name__ == "__main__":
    arquivos = sorted(str(p) for p in Path(sys.argv[1]).glob("*.pdf"))
    with get_context("spawn").Pool(4) as pool:
        r = dict(pool.imap_unordered(_um, arquivos, chunksize=8))
    Path(sys.argv[2]).write_text(json.dumps(r, ensure_ascii=False) + "\n", encoding="utf-8")
    print(len(r), "arquivos;", sum(1 for v in r.values() if v), "com texto oculto")
