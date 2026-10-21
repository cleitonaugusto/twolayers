"""Mede o método de perícia de documentos do kit (linha_do_tempo, custodia, peca) contra o corpus com gabarito.

    python3 validacao/medir.py [--saida validacao/resultados/<versão>]      (na raiz do kit, com o kit instalado)

O relatório leva a versão da ferramenta, a do kit, o Python e o hash do corpus: com os mesmos quatro, o resultado tem
de ser o mesmo (é isso que vai para a seção de metodologia do laudo e para o artigo).
"""

import argparse
import hashlib
import json
import platform
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import casos as cs  # noqa: E402
from twolayers import custodia  # noqa: E402
from twolayers import linha_do_tempo as lt  # noqa: E402
from twolayers import __version__ as VERSAO_KIT  # noqa: E402
from twolayers import peca as kit_peca  # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Placar:
    def __init__(self):
        self.m = defaultdict(lambda: {"vp": 0, "fp": 0, "fn": 0, "certo": 0, "total": 0})
        self.falhas = []

    def conta(self, metrica: str, caso: dict, certo: bool, esperado, obtido):
        d = self.m[metrica]
        d["total"] += 1
        d["certo"] += certo
        if not certo:
            self.falhas.append({"metrica": metrica, "caso": caso["id"], "descricao": caso["descricao"],
                                "esperado": esperado, "obtido": obtido, "lacuna_conhecida": caso.get("lacuna_conhecida")})

    def deteccao(self, metrica: str, caso: dict, vp: int, fp: int, fn: int, esperado, obtido):
        d = self.m[metrica]
        d["vp"], d["fp"], d["fn"] = d["vp"] + vp, d["fp"] + fp, d["fn"] + fn
        d["total"] += 1
        d["certo"] += fp == 0 and fn == 0
        if fp or fn:
            self.falhas.append({"metrica": metrica, "caso": caso["id"], "descricao": caso["descricao"],
                                "esperado": esperado, "obtido": obtido, "lacuna_conhecida": caso.get("lacuna_conhecida")})


def _comparar_ocultos(placar: Placar, metrica: str, caso: dict, esperados: list, obtidos: list[dict]):
    achou = [any(e["contem"] in o["texto"] for o in obtidos) for e in esperados]
    sobra = [o for o in obtidos if not any(e["contem"] in o["texto"] for e in esperados)]
    placar.deteccao(metrica, caso, sum(achou), len(sobra), len(achou) - sum(achou),
                    [e["contem"] for e in esperados], [o["texto"][:40] for o in obtidos])
    return achou


def medir_docx(placar: Placar, caso: dict):
    tl = lt.docx(caso["arquivo"])
    esp = caso["esperado"]
    if "ocultos" in esp:
        _comparar_ocultos(placar, "docx: texto oculto", caso, esp["ocultos"], tl["texto_oculto_por_sessao"])
        for e in esp["ocultos"]:
            o = next((o for o in tl["texto_oculto_por_sessao"] if e["contem"] in o["texto"]), None)
            if o is None or "sessao_texto" not in e:
                continue
            placar.conta("docx: sessão em que o texto entrou", caso, o["sessao_n"] == e["sessao_texto"],
                         e["sessao_texto"], o["sessao_n"])
            # o laudo diz "oculto ... em sessão N": é a afirmação de QUANDO foi escondido
            quando = o.get("sessao_ocultacao_n", o["sessao_n"])
            placar.conta("docx: sessão em que o texto foi escondido", caso, quando == e["sessao_ocultacao"],
                         e["sessao_ocultacao"], quando)
    if "ocultos" in esp:
        # o mesmo arquivo pelo verificador do kit (verificar-peca), o que o usuário roda antes de enviar a peça
        obtidos = [{"texto": " ".join(t.texto.split())} for t in kit_peca.ocultos_relevantes(kit_peca.extrair_docx(caso["arquivo"]))]
        _comparar_ocultos(placar, "verificador de peças (verificar-peca): texto oculto no Word", caso, esp["ocultos"], obtidos)
    if "alteracoes" in esp:
        obtido = defaultdict(int)
        for a in tl["alteracoes_rastreadas"]:
            obtido[a["tipo"]] += 1
        placar.conta("docx: alterações rastreadas (contagem por tipo)", caso, dict(obtido) == esp["alteracoes"],
                     esp["alteracoes"], dict(obtido))
    if "autores" in esp:
        autores = sorted({a["autor"] for a in tl["alteracoes_rastreadas"]})
        placar.conta("docx: autores das alterações", caso, autores == esp["autores"], esp["autores"], autores)
    if "comentarios" in esp:
        placar.conta("docx: comentários", caso, len(tl["comentarios"]) == esp["comentarios"], esp["comentarios"],
                     len(tl["comentarios"]))


def medir_pdf(placar: Placar, caso: dict, tmp: Path):
    esp = caso["esperado"]
    pasta = tmp / caso["id"]
    pasta.mkdir()
    estrutura = lt.pdf(caso["arquivo"], pasta)
    revs = estrutura["revisoes"]
    placar.conta("pdf: número de versões salvas", caso, len(revs) == esp["versoes"], esp["versoes"], len(revs))
    apos = estrutura.get("dados_apos_o_fim") is not None
    placar.conta("pdf: dados acrescentados depois do fim", caso, apos == esp.get("dados_apos_fim", False),
                 esp.get("dados_apos_fim", False), apos)
    for chave, metrica, sinal in (("aparece_na_versao", "pdf: versão em que o texto aparece", "+"),
                                  ("some_na_versao", "pdf: versão em que o texto some", "-")):
        for texto, versao in esp.get(chave, {}).items():
            obtida = next((r["n"] for r in revs if any(l.startswith(sinal) and texto in l
                                                        for l in r.get("mudou_em_relacao_a_anterior", []))), None)
            placar.conta(metrica, caso, obtida == versao, versao, obtida)
    if "ocultos" in esp:  # a mesma regra que decide o T1 do verificador de peças
        obtidos = [{"texto": " ".join(t.texto.split())} for t in kit_peca.ocultos_relevantes(kit_peca.extrair_pdf(caso["arquivo"]))]
        _comparar_ocultos(placar, "pdf: texto oculto", caso, esp["ocultos"], obtidos)
    if "comando_ia" in esp:
        t3 = next(a for a in kit_peca.verificar(caso["arquivo"])[0] if a.item == "T3")
        placar.conta("pdf: comando para IA (inclusive na camada de OCR)", caso, (t3.resultado == "RISCO") == esp["comando_ia"],
                     esp["comando_ia"], t3.resultado == "RISCO")


def medir_custodia(placar: Placar, tmp: Path):
    """Dois modos: só o encadeamento por hash, e com cada linha assinada pelo examinador + âncora tirada do relatório."""
    chave = tmp / "examinador" / "examinador.key"
    custodia.gerar_chave(chave)
    publica = custodia.carregar_publica(chave.with_suffix(".pub"))
    for modo, assinada in (("só encadeamento", False), ("assinada + âncora do laudo", True)):
        privada = custodia.carregar_privada(chave) if assinada else None
        for cid, descricao, integra, lacuna in cs.CUSTODIA:
            pasta = tmp / f"custodia-{assinada}" / cid
            evidencias = pasta / "evidencias"
            evidencias.mkdir(parents=True)
            registro = pasta / "custodia.jsonl"
            ev = evidencias / "E01-peca.pdf"
            cs.escrever_pdf(ev, [("Peca ficticia.", 12, cs.PRETO, 72, 700)])
            custodia.registrar(registro, "abertura", privada, objeto="validação", por="validador")
            custodia.registrar(registro, "recebimento", privada, id="E01", arquivo=ev.name, por="validador",
                               **custodia.hash_arquivo(ev))
            custodia.registrar(registro, "exame", privada, id="E01", por="validador")
            ancora = custodia.ancora(registro) if assinada else None  # o que o relatório entregue registrou
            linhas = registro.read_text(encoding="utf-8").splitlines()
            if cid == "cu-byte":
                ev.write_bytes(ev.read_bytes()[:-1] + b"#")
            elif cid == "cu-linha-editada":
                l2 = json.loads(linhas[1])
                l2["recebido_de"] = "outra pessoa"
                linhas[1] = json.dumps(l2, ensure_ascii=False)
            elif cid == "cu-linha-apagada":
                del linhas[1]
            elif cid == "cu-truncada":
                del linhas[-1]
            elif cid == "cu-forjada-no-fim":  # quem forja não tem a chave privada do examinador
                ultima = json.loads(linhas[-1])
                falsa = {"n": ultima["n"] + 1, "quando": ultima["quando"], "evento": "exame", "por": "intruso",
                         "id": "E01", "anterior": custodia.hash_linha(ultima)}
                linhas.append(json.dumps(falsa, ensure_ascii=False))
            if cid != "cu-byte":
                registro.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            problemas = custodia.conferir(registro, publica if assinada else None, ancora, evidencias)
            caso = {"id": f"{cid} ({modo})", "descricao": descricao, "lacuna_conhecida": None if assinada else lacuna}
            placar.conta(f"custódia: adulteração detectada ({modo})", caso, (not problemas) == integra,
                         "íntegra" if integra else "adulterada", "íntegra" if not problemas else "adulterada")


def rodar(saida: Path | None = None) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="validacao-"))
    try:
        (tmp / "corpus").mkdir()
        todos = cs.casos_docx(tmp / "corpus") + cs.casos_pdf(tmp / "corpus")
        reais = [c for c in cs.casos_reais() if c["arquivo"].exists()]
        for c in reais:
            if c["sha256"] and _sha(c["arquivo"]) != c["sha256"]:
                raise SystemExit(f"{c['id']}: o arquivo real mudou (SHA-256 diferente do gabarito)")
        todos += reais
        placar = Placar()
        for caso in todos:
            (medir_docx(placar, caso) if caso["tipo"] == "docx" else medir_pdf(placar, caso, tmp))
        medir_custodia(placar, tmp)
        corpus = hashlib.sha256("".join(sorted(f"{c['id']}:{_sha(c['arquivo'])}" for c in todos)).encode()).hexdigest()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    metricas = {}
    for nome, d in sorted(placar.m.items()):
        m = {"casos": d["total"], "acertos": d["certo"], "taxa_de_acerto": round(d["certo"] / d["total"], 3)}
        if d["vp"] + d["fp"] + d["fn"]:
            m.update({"vp": d["vp"], "fp": d["fp"], "fn": d["fn"],
                      "sensibilidade": round(d["vp"] / (d["vp"] + d["fn"]), 3) if d["vp"] + d["fn"] else None,
                      "precisao": round(d["vp"] / (d["vp"] + d["fp"]), 3) if d["vp"] + d["fp"] else None})
        metricas[nome] = m
    resultado = {
        "ferramenta": "linha_do_tempo + custodia + peca", "kit": f"twolayers {VERSAO_KIT}",
        "python": platform.python_version(), "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus_sha256": corpus, "casos": len(todos) + 2 * len(cs.CUSTODIA),
        "casos_reais": len(reais), "metricas": metricas, "falhas": placar.falhas,
    }
    if saida:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (saida / "relatorio.md").write_text(relatorio(resultado), encoding="utf-8")
    return resultado


def relatorio(r: dict) -> str:
    md = [f"# Validação do {r['kit']} ({r['ferramenta']})", "",
          f"{r['casos']} casos com gabarito ({r['casos_reais']} arquivos reais de Word/Acrobat/macOS dos projetos "
          f"Apache Tika e POI). Kit: {r['kit']}. Python {r['python']}. Corpus `{r['corpus_sha256'][:16]}…`. "
          f"Medido em {r['medido_em']}.", "",
          "| Afirmação da ferramenta | Casos | Acertos | Taxa | VP | FP | FN |", "|---|---|---|---|---|---|---|"]
    for nome, m in r["metricas"].items():
        md.append(f"| {nome} | {m['casos']} | {m['acertos']} | {m['taxa_de_acerto']:.0%} | {m.get('vp', '')} | "
                  f"{m.get('fp', '')} | {m.get('fn', '')} |")
    md += ["", "VP = achou o que existe; FP = acusou o que não existe; FN = deixou passar o que existe.", "",
           f"## Falhas ({len(r['falhas'])})", ""]
    for f in r["falhas"]:
        md.append(f"- **{f['caso']}** ({f['metrica']}): {f['descricao']}. Esperado `{f['esperado']}`, obtido "
                  f"`{f['obtido']}`." + (f" Lacuna conhecida: {f['lacuna_conhecida']}." if f["lacuna_conhecida"] else
                                         " **Falha não prevista.**"))
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", type=Path, default=Path(__file__).resolve().parent / "resultados")
    args = ap.parse_args()
    r = rodar(args.saida)
    print(relatorio(r))
