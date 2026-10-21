"""Verificação INDEPENDENTE e automática das acusações de texto oculto (rodada 5), sem avaliador humano.

    PYTHONPATH=~/kit-auditoria-mcp/src python3 -I validacao/segundo-avaliador/ocr_independente.py <pasta-do-pacote>

Para cada arquivo acusado, a página é desenhada por OUTRO motor de PDF (Poppler, pdftoppm — a ferramenta usa PDFium),
só a área que o leitor mostra (CropBox, como Acrobat e navegadores), e lida por OCR (Tesseract), que vê só os pixels. Se o OCR encontra o trecho acusado, ele está visível: a acusação estava
errada. Se não encontra, o trecho de fato não aparece.

Calibração: na mesma página, o OCR também procura um trecho que a ferramenta considera VISÍVEL (controle). A taxa com
que o OCR acha os controles mede quanto ele deixa escapar; sem ela, "o OCR não achou" não provaria nada.
Saída: resultado-ocr.json na pasta do gabarito interno (2º argumento; padrão: ao lado deste script).
"""

import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DPI = 300
ACHOU = 0.8  # semelhança mínima entre o trecho e uma janela do texto lido pelo OCR
ESTRITO = __import__("os").environ.get("OCR_REGRA", "estrita") == "estrita"  # OCR_REGRA=semelhanca: regra da rodada 6


def palavras(texto: str) -> list[str]:
    return [p for p in re.findall(r"[^\W_]+", re.sub(r"\(cid:\d+\)", " ", texto).lower()) if len(p) >= 2]


def _em_ordem(alvo: list[str], janela: list[str]) -> bool:
    """As palavras do trecho aparecem na janela na mesma ordem (cada uma com até um erro de leitura do OCR, ou partida
    em duas). Trecho de até 3 palavras: todas; mais longo: pode faltar uma (símbolo que o OCR não lê, como m³)."""
    def igual(p, j):
        if difflib.SequenceMatcher(None, p, janela[j]).ratio() >= ACHOU:
            return 1
        if j + 1 < len(janela) and difflib.SequenceMatcher(None, p, janela[j] + janela[j + 1]).ratio() >= ACHOU:
            return 2
        return 0

    achadas, j = 0, 0
    for p in alvo:
        k = j
        while k < len(janela) and not igual(p, k):
            k += 1
        if k < len(janela):
            achadas += 1
            j = k + igual(p, k)
    return achadas >= (len(alvo) if len(alvo) <= 3 else len(alvo) - 1)


def encontra(trecho: str, lido: str, estrito: bool = ESTRITO) -> bool | None:
    """True/False; None se o trecho não tem palavras suficientes para uma busca justa.

    estrito: além da semelhança do conjunto, exige as palavras do trecho na mesma ordem (a regra só por semelhança
    aceitou "55 system summary" — número da página + título — como se fosse a legenda "Table 1. System Summary.")."""
    alvo = palavras(trecho)[:10]
    if len(alvo) < 2 and not (alvo and len(alvo[0]) >= 5):
        return None
    texto = palavras(lido)
    n, frase = len(alvo), " ".join(alvo)
    folga = 2 if estrito else 0  # a janela pode ter palavras a mais (OCR que quebra uma palavra em duas)
    for i in range(max(1, len(texto) - n + 1)):
        janela = texto[i:i + n + folga]
        if difflib.SequenceMatcher(None, frase, " ".join(janela[:n])).ratio() >= ACHOU or (
                estrito and difflib.SequenceMatcher(None, frase, " ".join(janela)).ratio() >= ACHOU):
            if not estrito or _em_ordem(alvo, janela):
                return True
    return False


def ocr_da_pagina(pdf: Path, pagina: int, tmp: Path) -> str:
    base = tmp / "pag"
    subprocess.run(["pdftoppm", "-cropbox", "-r", str(DPI), "-f", str(pagina), "-l", str(pagina), "-png", "-singlefile",
                    str(pdf), str(base)], check=True, capture_output=True, timeout=120)
    saida = subprocess.run(["tesseract", f"{base}.png", "stdout", "-l", "eng+por"], capture_output=True, text=True,
                           timeout=180)
    return saida.stdout


def controle_visivel(pdf: Path, pagina: int) -> str:
    """Um trecho que a ferramenta considera visível, na mesma página, com pelo menos 3 palavras."""
    from twolayers import peca as kp
    for t in kp.extrair_pdf(pdf):
        if t.pagina == pagina and not t.motivo:
            for linha in t.texto.splitlines():
                if len(palavras(linha)) >= 4:
                    return " ".join(linha.split())[:60]
    return ""


def copia_visivel(pdf: Path, pagina: int, trecho: str) -> bool:
    """O trecho acusado também existe como texto VISÍVEL na mesma página (ex.: título duplicado escondido)? Então o OCR
    achar as palavras não prova que a acusação está errada: o caso é inconclusivo."""
    from twolayers import peca as kp
    visivel = "\n".join(t.texto for t in kp.extrair_pdf(pdf) if t.pagina == pagina and not t.motivo)
    return bool(encontra(trecho, visivel))


def main(pacote: Path, interno: Path = AQUI) -> int:
    import logging
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    gabarito = json.loads((interno / "gabarito-interno.json").read_text(encoding="utf-8"))
    resultados = {}
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for codigo, g in sorted(gabarito.items()):
            pdf = pacote / "pdfs" / f"{codigo}.pdf"
            try:
                lido = ocr_da_pagina(pdf, g["pagina"], tmp)
                controle = controle_visivel(pdf, g["pagina"])
                resultados[codigo] = {"classificacao": g["classificacao"], "motivo": g["motivo"],
                                      "acusado_visivel_no_ocr": encontra(g["trecho"], lido),
                                      "controle": controle, "controle_visivel_no_ocr": encontra(controle, lido)}
                if resultados[codigo]["acusado_visivel_no_ocr"]:
                    resultados[codigo]["copia_visivel_na_pagina"] = copia_visivel(pdf, g["pagina"], g["trecho"])
            except Exception as e:  # página que o Poppler ou o OCR não processam
                resultados[codigo] = {"classificacao": g["classificacao"], "erro": str(e)[:120]}
            print(codigo, resultados[codigo].get("acusado_visivel_no_ocr"), resultados[codigo].get("controle_visivel_no_ocr"),
                  flush=True)
    (interno / "resultado-ocr.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    resumo(resultados)
    return 0


def resumo(r: dict) -> None:
    from math import sqrt
    ok = {k: v for k, v in r.items() if "erro" not in v}
    controles = [v["controle_visivel_no_ocr"] for v in ok.values() if v.get("controle_visivel_no_ocr") is not None]
    avaliaveis = {k: v for k, v in ok.items() if v["acusado_visivel_no_ocr"] is not None}
    visiveis = [k for k, v in avaliaveis.items() if v["acusado_visivel_no_ocr"]]
    n, x = len(avaliaveis), len(avaliaveis) - len(visiveis)

    def wilson(x, n, z=1.96):
        if not n:
            return (0, 0)
        p = x / n
        c = (p + z * z / (2 * n)) / (1 + z * z / n)
        m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return (round(c - m, 3), round(c + m, 3))

    print(f"\nOCR achou {sum(controles)}/{len(controles)} controles visíveis (sensibilidade do OCR)")
    print(f"acusações avaliáveis: {n}; o OCR NÃO viu o trecho em {x} ({x / n:.0%}); IC95% {wilson(x, n)}" if n else "")
    inconclusivos = [k for k in visiveis if ok[k].get("copia_visivel_na_pagina")]
    print("o OCR viu, mas há cópia visível do mesmo texto na página (inconclusivo):", inconclusivos)
    print("o OCR viu, sem cópia visível (acusação ERRADA):", [k for k in visiveis if k not in inconclusivos])
    print("sem trecho buscável:", [k for k, v in ok.items() if v["acusado_visivel_no_ocr"] is None])
    print("erros:", [k for k, v in r.items() if "erro" in v])


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else AQUI))
