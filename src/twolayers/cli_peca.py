"""verificar-peca: checa uma peça (PDF, DOCX ou texto) antes do protocolo — texto oculto, injeção de prompt, o que o
arquivo vaza (alterações rastreadas, comentários, metadados, versões anteriores, macros) e citações."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, checagem, relatorio
from .peca import verificar
from .achados import NA, OK, REVISAR, RISCO

ORDEM = {RISCO: 0, REVISAR: 1, OK: 2, NA: 3}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="verificar-peca", description=__doc__)
    p.add_argument("arquivos", nargs="+", type=Path, help="peças a verificar (.pdf, .docx, .txt)")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    p.add_argument("--html", type=Path, metavar="ARQUIVO", help="relatório HTML: arquivo .html (uma peça) ou pasta (um relatório por peça)")
    p.add_argument("--semantico", metavar="PASTA_DO_MODELO", nargs="?", const="",
                   help="liga o detector local de injeção por significado (pasta do modelo ou TWOLAYERS_MODELO)")
    p.add_argument("--checagem", action="store_true",
                   help="parecer curto em linguagem de escritório: o que corrigir e o que conferir antes de enviar")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    semantico = None
    if args.semantico is not None:
        from .semantico import DetectorSemantico
        try:
            semantico = DetectorSemantico(args.semantico or None)
        except RuntimeError as e:
            p.error(str(e))
    pior = 0
    saida_json = []
    for arq in args.arquivos:
        arq = arq.expanduser()
        if not arq.is_file():
            p.error(f"não encontrado: {arq}")
        try:
            achados, info = verificar(arq, semantico)
        except (RuntimeError, ValueError, OSError) as e:
            print(f"{arq.name}: não consegui ler ({e})", file=sys.stderr)
            pior = max(pior, 2)
            continue
        if any(a.resultado == RISCO and a.sev == "A" for a in achados):
            pior = max(pior, 1)
        if args.json:
            saida_json.append({"arquivo": arq.name, **info, "achados": [a.como_dict() for a in achados]})
        elif args.checagem:
            print(checagem.texto(arq.name, achados) + "\n")
        else:
            print(f"Verificação de peça — {arq.name}\n")
            for a in sorted(achados, key=lambda a: (ORDEM[a.resultado], a.item)):
                print(f"[{a.resultado:7}] {a.item:3} {a.titulo}")
                for e in a.evidencias[:10]:
                    print(f"          - {e}")
                if len(a.evidencias) > 10:
                    print(f"          ... e mais {len(a.evidencias) - 10}")
            print()
        if args.html:
            destino = args.html.expanduser()
            if destino.suffix.lower() != ".html" or len(args.arquivos) > 1:
                destino.mkdir(parents=True, exist_ok=True)
                destino = destino / f"{arq.stem}.html"
            vazamentos = sum(a.resultado == RISCO and a.item.startswith("V") for a in achados)
            cartoes = ([(info["paginas"], "páginas")] if info["paginas"] else []) + [(vazamentos, "vazamentos pelo arquivo")]
            html = relatorio.gerar(achados, [], arq.name, titulo="Verificação de peça antes do protocolo",
                                   nota=relatorio.NOTA_PECA, cartoes=cartoes)
            destino.write_text(html, encoding="utf-8")
            print(f"Relatório HTML gravado em {destino}.", file=sys.stderr)
    if args.json:
        print(json.dumps(saida_json, ensure_ascii=False, indent=2))
    return pior


if __name__ == "__main__":
    sys.exit(main())
