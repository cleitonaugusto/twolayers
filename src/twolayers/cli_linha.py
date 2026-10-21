"""linha-do-tempo: quando o conteúdo escondido entrou no documento e quando foi escondido.

No Word, pelas sessões de edição (rsid); no PDF, pelas versões salvas dentro do arquivo.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__, linha_do_tempo


def _sessao(n, total) -> str:
    return f"sessão {n} de {total}" if n else "sessão não registrada"


def _docx(arq: Path, r: dict) -> None:
    total = r["sessoes_de_edicao"]
    print(f"{arq.name} — Word, {total} sessões de edição registradas\n")
    ocultos = r["texto_oculto_por_sessao"]
    print(f"Texto escondido: {len(ocultos)}")
    for i, o in enumerate(ocultos, 1):
        print(f'\n  {i}. "{" ".join(o["texto"].split())[:90]}"')
        print(f"     como: {o['motivo']}")
        n, m = o.get("sessao_n"), o.get("sessao_ocultacao_n")
        print(f"     digitado na {_sessao(n, total)}" + (" (a primeira: pode ter vindo do modelo)" if o.get("sessao_raiz") else ""))
        if not o.get("ocultacao_registrada"):
            print("     escondido: o Word não registrou a sessão da última mudança de formatação")
        elif m == n:
            print(f"     escondido na mesma sessão: entrou no documento JÁ escondido ({_sessao(m, total)})")
        else:
            print(f"     escondido DEPOIS de digitado: última mudança de formatação na {_sessao(m, total)}")
    if r["alteracoes_rastreadas"]:
        print(f"\nAlterações rastreadas: {len(r['alteracoes_rastreadas'])}")
    if r["comentarios"]:
        print(f"Comentários: {len(r['comentarios'])}")
    print("\nAs sessões dão a ORDEM das edições, não a hora nem a pessoa. A última mudança de formatação pode ser "
          "posterior à que escondeu o texto.")


def _pdf(arq: Path, r: dict) -> None:
    revs = r["revisoes"]
    extra = " (linearizado: o rodapé da primeira página não conta como versão)" if r["linearizado"] else ""
    print(f"{arq.name} — PDF, {len(revs)} versão(ões) salva(s) dentro do arquivo{extra}")
    for v in revs:
        data = v["info"].get("ModDate") or v["info"].get("CreationDate") or "sem data no arquivo"
        print(f"\n  versão {v['n']} (até o byte {v['ate_byte']}, {data})")
        if v.get("erro"):
            print(f"     não abre sozinha: {v['erro'][:80]}")
        for linha in v.get("mudou_em_relacao_a_anterior", []):
            sinal = "entrou " if linha.startswith("+") else "saiu   "
            print(f"     {sinal} {linha[1:][:100]}")
    if r["dados_apos_o_fim"]:
        d = r["dados_apos_o_fim"]
        print(f"\nDados acrescentados depois do fim: {d['bytes']} bytes (não são uma versão)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="linha-do-tempo", description=__doc__)
    p.add_argument("arquivo", type=Path, help="documento .docx ou .pdf")
    p.add_argument("--json", action="store_true", help="saída estruturada")
    p.add_argument("--version", action="version", version=f"twolayers {__version__}")
    args = p.parse_args(argv)
    arq = args.arquivo.expanduser()
    if not arq.is_file():
        p.error(f"não encontrado: {arq}")
    sufixo = arq.suffix.lower()
    if sufixo in (".docx", ".docm", ".dotx", ".dotm"):
        r = linha_do_tempo.docx(arq)
    elif sufixo == ".pdf":
        with tempfile.TemporaryDirectory() as pasta:
            r = linha_do_tempo.pdf(arq, Path(pasta))
    else:
        print(f"{arq.name}: formato não suportado (use .docx ou .pdf)", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif r["formato"] == "docx":
        _docx(arq, r)
    else:
        _pdf(arq, r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
