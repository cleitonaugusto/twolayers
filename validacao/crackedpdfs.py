"""Avaliação "a frio" no benchmark público CrackedPDFs (Thienpreecha e Subramanian, 2026, arXiv:2607.19396; MIT).

    python3 validacao/crackedpdfs.py <resultado do volume.py no split de teste> <metadata.jsonl> [--saida resumo.json]

A ferramenta não foi treinada nem ajustada no benchmark. Regras de decisão comparadas:
  instrucao       acusou instrução para IA (T3)
  oculto          acusou texto oculto (T1)
  oculto_e_instr  as duas (texto oculto E instrução)
  oculto_ou_instr qualquer uma
Métricas como no artigo deles: precisão, cobertura (recall) e F1 no split de teste inteiro (injetado contra os dois
tipos de benigno), taxa de acusação nos benignos originais e nos confundidores estruturais, acerto pareado (acusa o
injetado e não o confundidor do mesmo trio) e cobertura por família de ataque.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REGRAS = {
    "instrucao": lambda a: a.get("T3") == "RISCO",
    "oculto": lambda a: a.get("T1") == "RISCO",
    "oculto_e_instr": lambda a: a.get("T1") == "RISCO" and a.get("T3") == "RISCO",
    "oculto_ou_instr": lambda a: a.get("T1") == "RISCO" or a.get("T3") == "RISCO",
}


def avaliar(resultado: Path, metadata: Path) -> dict:
    meta = {}
    for linha in metadata.read_text(encoding="utf-8").splitlines():
        r = json.loads(linha)
        meta[r["pdf_id"]] = r
    res = json.loads(resultado.read_text(encoding="utf-8"))["resultados"]
    por_id = {r["arquivo"][:-4]: r for r in res}  # "<pdf_id>.pdf"
    saida = {"arquivos": len(por_id), "sem_leitura": sum("achados" not in r for r in por_id.values())}
    for nome, regra in REGRAS.items():
        vp = fp = fn = vn = 0
        acusa = {}
        por_papel = defaultdict(lambda: [0, 0])
        por_familia = defaultdict(lambda: [0, 0])
        for pid, r in por_id.items():
            m = meta[pid]
            pos = bool("achados" in r and regra(r["achados"]))  # sem leitura = não acusou
            acusa[pid] = pos
            por_papel[m["pdf_role"]][0] += pos
            por_papel[m["pdf_role"]][1] += 1
            if m["label"] == 1:
                vp += pos
                fn += not pos
                por_familia[m["attack_family"]][0] += pos
                por_familia[m["attack_family"]][1] += 1
            else:
                fp += pos
                vn += not pos
        prec = vp / (vp + fp) if vp + fp else 0.0
        rec = vp / (vp + fn) if vp + fn else 0.0
        trios = defaultdict(dict)
        for pid in por_id:
            m = meta[pid]
            trios[m["sample_id"]][m["pdf_role"]] = acusa[pid]
        pares = [t for t in trios.values() if "injected_attack" in t and "benign_confounder" in t]
        saida[nome] = {
            "precisao": round(prec, 3), "cobertura": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "vp": vp, "fp": fp, "fn": fn, "vn": vn,
            "taxa_acusacao_por_papel": {k: f"{a}/{n}" for k, (a, n) in sorted(por_papel.items())},
            "acerto_pareado_injetado_vs_confundidor": round(
                sum(t["injected_attack"] and not t["benign_confounder"] for t in pares) / len(pares), 3) if pares else None,
            "cobertura_por_familia": {k: f"{a}/{n}" for k, (a, n) in sorted(por_familia.items())},
        }
    return saida


if __name__ == "__main__":
    r = avaliar(Path(sys.argv[1]), Path(sys.argv[2]))
    if "--saida" in sys.argv:
        Path(sys.argv[sys.argv.index("--saida") + 1]).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    for nome in REGRAS:
        m = r[nome]
        print(f"{nome:16} P={m['precisao']:.3f} R={m['cobertura']:.3f} F1={m['f1']:.3f} pareado={m['acerto_pareado_injetado_vs_confundidor']} "
              f"papéis={m['taxa_acusacao_por_papel']}")
