"""Gera os diagramas do README em docs/img/ (PNG para o GitHub, SVG em vetor).

    python3 docs/figuras/gerar_figuras.py

Precisa só do matplotlib. As fontes (OFL) estão em docs/figuras/fontes; livrofig.py confere legibilidade
(corpo mínimo, textos encostados, texto sobre seta) e recusa a figura se algo falhar.
"""

from pathlib import Path

import livrofig as lf

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI.parent / "img"


def verificar_peca():
    """O que o verificar-peca encontra num arquivo, sem o documento sair do computador."""
    f, ax = lf.canvas(100, 60)
    lf.text(ax, 50, 57, "O que o verificar-peca encontra antes de o arquivo sair do escritório",
            size=lf.PT_TITLE, weight="semibold")

    lf.box(ax, 36, 22, 28, 22, "peticao.pdf", "o que aparece\nna tela", header=True)

    esquerda = [("Texto oculto", "branco, minúsculo, sob tarja"),
                ("Comando para IA", "\"ignore as instruções…\""),
                ("Caracteres invisíveis", "Unicode tag, bidi")]
    direita = [("Alterações rastreadas", "o texto apagado continua lá"),
               ("Comentários", "notas internas do escritório"),
               ("Metadados", "autor, caminhos internos"),
               ("Versões anteriores", "e macros, JavaScript")]
    for i, (t, s) in enumerate(esquerda):
        y = 42 - i * 12
        lf.box(ax, 2, y, 26, 9, t, s, kind="accent")
        lf.arrow(ax, (28, y + 4.5), (36, 33), lw=0.7, color=lf.GRAY, style="-")
    for i, (t, s) in enumerate(direita):
        y = 45 - i * 10.5
        lf.box(ax, 72, y, 26, 8.5, t, s, kind="accent")
        lf.arrow(ax, (72, y + 4.25), (64, 33), lw=0.7, color=lf.GRAY, style="-")

    lf.box(ax, 14, 2, 72, 7, "Roda no seu computador: o documento do cliente não vai para a internet",
           kind="dashed", size=lf.PT_SUB)
    return f


if __name__ == "__main__":
    lf.setup(fontes=str(AQUI / "fontes"), accent="#1f5f7a", accent_fill="#e1eef4")
    SAIDA.mkdir(exist_ok=True)
    lf.save(verificar_peca(), str(SAIDA / "verificar-peca-o-que-encontra"))
    print("figuras gravadas em", SAIDA)
