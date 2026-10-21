"""Falso positivo em volume: roda o verificador de peças e a linha do tempo em documentos reais, sem gabarito.

    PYTHONPATH=~/kit-auditoria-mcp/src python3 -I validacao/volume.py <pasta> [--saida arquivo.json] [--limite N]

Em documentos comuns quase nada deveria ser acusado. Cada acusação sai com o motivo e o arquivo, para revisão manual
(é a revisão que separa acerto de falso positivo). Também mede travamentos, erros de leitura e tempo por arquivo.
Corpus de referência: Govdocs1 (digitalcorpora.org), arquivos reais de sites do governo americano.
"""

import argparse
import logging
import json
import multiprocessing as mp
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = {".pdf", ".docx", ".doc", ".odt", ".rtf"}
TEMPO_MAXIMO = 60


def _um(caminho: str) -> dict:
    import logging
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    sys.path.insert(0, str(RAIZ / "src"))
    from twolayers import linha_do_tempo as lt, peca as kit_peca
    arq = Path(caminho)
    r = {"arquivo": arq.name, "bytes": arq.stat().st_size}
    inicio = time.perf_counter()
    try:
        achados, _ = kit_peca.verificar(arq)
        r["achados"] = {a.item: a.resultado for a in achados if a.resultado in ("RISCO", "REVISAR")}
        r["evidencias"] = {a.item: a.evidencias[:3] for a in achados if a.resultado == "RISCO"}
        if arq.suffix.lower() == ".pdf":
            with tempfile.TemporaryDirectory() as t:
                e = lt.pdf(arq, Path(t))
            r["versoes"] = len(e["revisoes"])
            r["linearizado"] = e["linearizado"]
            r["dados_apos_o_fim"] = e["dados_apos_o_fim"] is not None
    except kit_peca.FormatoNaoSuportado as ex:
        r["recusado"] = str(ex)
    except Exception as ex:  # o que um documento real derruba é exatamente o que precisamos saber
        r["erro"] = f"{type(ex).__name__}: {str(ex)[:160]}"
    r["segundos"] = round(time.perf_counter() - inicio, 2)
    return r


def _filho(caminho: str, fila):
    fila.put(_um(caminho))


def rodar(pasta: Path, limite: int | None = None, processos: int = 4, parcial: Path | None = None) -> dict:
    """Um processo por arquivo, encerrado à força se passar de TEMPO_MAXIMO (leitor travado não prende os outros)."""
    arquivos = sorted(p for p in pasta.rglob("*") if p.suffix.lower() in TIPOS)[:limite]
    ctx = mp.get_context("spawn")
    pendentes, rodando, resultados = list(arquivos), [], []
    diario = parcial.open("w", encoding="utf-8") if parcial else None  # cada resultado vai ao disco na hora
    while pendentes or rodando:
        while pendentes and len(rodando) < processos:
            a = pendentes.pop(0)
            fila = ctx.Queue()
            proc = ctx.Process(target=_filho, args=(str(a), fila), daemon=True)
            proc.start()
            rodando.append((a, proc, fila, time.monotonic()))
        for item in list(rodando):
            a, proc, fila, inicio = item
            if not fila.empty() or not proc.is_alive():
                try:  # o filho pode ter terminado logo depois de pôr o resultado na fila
                    resultados.append(fila.get(timeout=5))
                except Exception:
                    resultados.append({"arquivo": a.name, "erro": f"terminou sem resultado (código {proc.exitcode})"})
                proc.join(1)
            elif time.monotonic() - inicio > TEMPO_MAXIMO:
                proc.kill()
                proc.join(1)
                resultados.append({"arquivo": a.name, "erro": f"travou (mais de {TEMPO_MAXIMO} s)"})
            else:
                continue
            rodando.remove(item)
            if diario:
                diario.write(json.dumps(resultados[-1], ensure_ascii=False) + "\n")
                diario.flush()
            if len(resultados) % 50 == 0:
                print(f"{len(resultados)}/{len(arquivos)}", file=sys.stderr, flush=True)
        time.sleep(0.05)
    if diario:
        diario.close()
    return resumo(resultados)


def resumo(resultados: list[dict]) -> dict:
    ok = [r for r in resultados if "achados" in r]
    acusados = Counter(item for r in ok for item, res in r["achados"].items() if res == "RISCO")
    motivos = Counter()
    for r in ok:
        for ev in r.get("evidencias", {}).get("T1", []):
            motivos[ev.split(" — ")[-1].split(":")[0].strip()] += 1
    tempos = sorted(r["segundos"] for r in ok)
    return {
        "arquivos": len(resultados), "lidos": len(ok), "recusados_por_formato": sum("recusado" in r for r in resultados),
        "erros": sum("erro" in r for r in resultados),
        "com_algum_risco": sum(any(v == "RISCO" for v in r["achados"].values()) for r in ok),
        "risco_por_item": dict(acusados.most_common()), "motivos_T1": dict(motivos.most_common()),
        "pdf_com_mais_de_uma_versao": sum(r.get("versoes", 1) > 1 for r in ok),
        "pdf_linearizados": sum(bool(r.get("linearizado")) for r in ok),
        "pdf_dados_apos_o_fim": sum(bool(r.get("dados_apos_o_fim")) for r in ok),
        "tempo_mediano_s": tempos[len(tempos) // 2] if tempos else None,
        "tempo_p95_s": tempos[int(len(tempos) * 0.95)] if tempos else None,
        "resultados": resultados,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--limite", type=int)
    args = ap.parse_args()
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    r = rodar(args.pasta, args.limite, parcial=args.saida.with_suffix(".jsonl") if args.saida else None)
    if args.saida:
        args.saida.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if k != "resultados"}, ensure_ascii=False, indent=1))
