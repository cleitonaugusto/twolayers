"""Etapa 2: o detector por significado (modelo local, calibrado em português, SEM ajuste no benchmark) julga se o texto
oculto é uma instrução dirigida a uma IA. Compara a regra "oculto E instrução por significado" com as do kit.

    PYTHONPATH=~/kit-auditoria-mcp/src <venv-semantico>/bin/python validacao/crackedpdfs_semantico.py \
        <ocultos.json> <metadata.jsonl> <modelo> [--saida resumo.json]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from twolayers.semantico import DetectorSemantico

ocultos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
meta = {}
for linha in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    r = json.loads(linha)
    meta[r["pdf_id"]] = r
det = DetectorSemantico(sys.argv[3])
acusa = {}
for pid, texto in ocultos.items():
    acusa[pid] = bool(texto) and bool(det.analisar(texto))
vp = sum(acusa[p] for p in acusa if meta[p]["label"] == 1)
fn = sum(not acusa[p] for p in acusa if meta[p]["label"] == 1)
fp = sum(acusa[p] for p in acusa if meta[p]["label"] == 0)
prec = vp / (vp + fp) if vp + fp else 0
rec = vp / (vp + fn) if vp + fn else 0
papel = defaultdict(lambda: [0, 0])
familia = defaultdict(lambda: [0, 0])
trios = defaultdict(dict)
for p, a in acusa.items():
    m = meta[p]
    papel[m["pdf_role"]][0] += a
    papel[m["pdf_role"]][1] += 1
    trios[m["sample_id"]][m["pdf_role"]] = a
    if m["label"] == 1:
        familia[m["attack_family"]][0] += a
        familia[m["attack_family"]][1] += 1
pares = [t for t in trios.values() if "injected_attack" in t and "benign_confounder" in t]
r = {"regra": "oculto_e_instrucao_por_significado", "limiar": det.limiar, "precisao": round(prec, 3),
     "cobertura": round(rec, 3), "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0,
     "vp": vp, "fp": fp, "fn": fn,
     "taxa_acusacao_por_papel": {k: f"{a}/{n}" for k, (a, n) in sorted(papel.items())},
     "acerto_pareado_injetado_vs_confundidor": round(sum(t["injected_attack"] and not t["benign_confounder"] for t in pares) / len(pares), 3),
     "cobertura_por_familia": {k: f"{a}/{n}" for k, (a, n) in sorted(familia.items())}}
if "--saida" in sys.argv:
    Path(sys.argv[sys.argv.index("--saida") + 1]).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(r, ensure_ascii=False, indent=1))
