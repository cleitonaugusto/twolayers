"""livrofig: figuras de livro técnico, desenhadas no tamanho
em que vão ser impressas e conferidas antes de salvar.

A regra que mais pesa: a figura nasce com a largura da mancha de texto (5 in),
então `fontsize=8` é 8 pt no papel. Nada de desenhar em 10 in e deixar o
navegador encolher: é assim que os rótulos viram 5 pt.

Uso mínimo:

    import livrofig as lf
    lf.setup(fontes="fontes")            # registra as fontes do livro
    f, ax = lf.canvas(100, 50)           # 100 x 50 unidades, largura = mancha
    lf.box(ax, 5, 20, 25, 10, "Agente", "com shell")
    lf.arrow(ax, (30, 25), (50, 25), label="token")
    lf.save(f, "images/fig-1-1-exemplo")  # confere, depois grava .svg e .png

`save` recusa a figura (FiguraRuim) se algum texto ficar abaixo de MIN_PT,
encostar em outro texto, sair pela borda de uma caixa, ficar em cima de uma
seta ou linha sem fundo, ou usar um glifo que a fonte não tem.
"""
import logging
import os
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.text import Text

# Geometria de livro técnico (7 x 9,19 in, margens de 1 in).
TEXT_W = 5.0          # largura da mancha, em polegadas
MIN_PT = 7.0          # menor corpo legível numa figura impressa
PAD_PT = 2.0          # folga mínima entre o texto e o filete da caixa
DPI_PNG = 400         # 5 in x 400 = 2000 px: sobra para 300 dpi impresso

# Paleta: tinta, cinzas, uma cor de destaque. Quem usa pode trocar ACCENT.
INK, GRAY, LIGHT, FILL, WHITE = "#1a1a1a", "#5f6670", "#c9cdd2", "#eef1f4", "#ffffff"
ACCENT, ACCENT_FILL = "#b5482a", "#f6e3dc"

SANS = ["Fira Sans Condensed", "DejaVu Sans"]   # a segunda cobre ✓ ✗ ↔
MONO = ["Ubuntu Mono", "DejaVu Sans Mono"]

# Tamanhos padrão, em pt de papel.
PT_TITLE, PT_LABEL, PT_SUB, PT_NOTE, PT_CODE = 9.5, 8.5, 7.5, 7.5, 7.5


class FiguraRuim(Exception):
    pass


def setup(fontes=None, accent=None, accent_fill=None):
    """Registra os .ttf de `fontes` e aplica o estilo. Chame uma vez."""
    global ACCENT, ACCENT_FILL
    if fontes and os.path.isdir(fontes):
        for name in sorted(os.listdir(fontes)):
            if name.lower().endswith((".ttf", ".otf")):
                font_manager.fontManager.addfont(os.path.join(fontes, name))
    if accent:
        ACCENT = accent
    if accent_fill:
        ACCENT_FILL = accent_fill
    plt.rcParams.update({
        "font.family": SANS,
        "font.size": PT_LABEL,
        "text.color": INK,
        "axes.edgecolor": GRAY,
        "axes.labelcolor": INK,
        "axes.labelsize": PT_LABEL,
        "xtick.color": GRAY,
        "ytick.color": GRAY,
        "xtick.labelsize": PT_SUB,
        "ytick.labelsize": PT_SUB,
        "figure.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "svg.fonttype": "path",     # o SVG não depende das fontes de quem abre
        "axes.unicode_minus": True,
    })


def canvas(w, h, width=TEXT_W):
    """Desenho em unidades livres (w x h), com a largura real da mancha."""
    f, ax = plt.subplots(figsize=(width, width * h / w))
    f.subplots_adjust(0, 0, 1, 1)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    return f, ax


def chart(height=2.6, width=TEXT_W):
    """Gráfico de dados com a largura da mancha."""
    f, ax = plt.subplots(figsize=(width, height))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return f, ax


_STYLES = {
    #        face         edge    ls            lw
    "plain": (WHITE, INK, "-", 0.9),
    "gray": (FILL, INK, "-", 0.9),
    "accent": (ACCENT_FILL, ACCENT, "-", 1.1),
    "dashed": (WHITE, GRAY, (0, (4, 3)), 0.8),
    "ghost": (WHITE, LIGHT, "-", 0.8),
    "dark": (INK, INK, "-", 0.9),
}


def box(ax, x, y, w, h, title="", sub=None, kind="plain", size=PT_LABEL, align="center", r=1.0,
        header=False, mono=False):
    """Caixa de cantos arredondados. header=True põe o título numa faixa branca
    sobre o corpo cinza."""
    face, edge, ls, lw = dict(_STYLES, accent=(ACCENT_FILL, ACCENT, "-", 1.1))[kind]
    if header:
        face = FILL if kind == "plain" else face
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=face, ec=edge, lw=lw, ls=ls, zorder=2)
    p._livrofig_box = True
    ax.add_patch(p)
    color = WHITE if kind == "dark" else (ACCENT if kind == "accent" else INK)
    tx = x + w / 2 if align == "center" else x + 1.2
    ha = "center" if align == "center" else "left"
    fam = MONO if mono else SANS
    if header and title:
        hh = min(h * 0.42, 7.5)
        hp = FancyBboxPatch((x, y + h - hh), w, hh, boxstyle=f"round,pad=0,rounding_size={r}",
                            fc=WHITE, ec=edge, lw=lw, zorder=2.1)
        hp._livrofig_box = True
        ax.add_patch(hp)
        text(ax, tx, y + h - hh / 2, title, size=size, color=INK, ha=ha, weight="semibold")
        if sub:
            text(ax, tx, y + (h - hh) / 2, sub, size=PT_SUB, color=INK, ha=ha, family=fam)
        return p
    if sub:
        text(ax, tx, y + h * 0.62, title, size=size, color=color, ha=ha, weight="semibold", family=fam)
        text(ax, tx, y + h * 0.28, sub, size=PT_SUB, color=(LIGHT if kind == "dark" else GRAY), ha=ha)
    elif title:
        text(ax, tx, y + h / 2, title, size=size, color=color, ha=ha, weight="semibold", family=fam)
    return p


def arrow(ax, a, b, color=INK, lw=0.9, style="-|>", ls="-", rad=0.0, label=None, lpos=0.5,
          loff=(0, 0), lsize=PT_SUB, lcolor=None):
    """Seta reta ou curva (rad). O rótulo vai sobre um fundo branco, centrado
    no ponto lpos da seta e deslocado por loff (unidades do desenho)."""
    p = FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=9, color=color, lw=lw, ls=ls,
                        connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0, zorder=2.5)
    ax.add_patch(p)
    if label:
        mx = a[0] + (b[0] - a[0]) * lpos + loff[0]
        my = a[1] + (b[1] - a[1]) * lpos + loff[1]
        text(ax, mx, my, label, size=lsize, color=lcolor or color, bg=True)
    return p


def text(ax, x, y, s, size=PT_LABEL, color=INK, ha="center", va="center", weight="normal",
         style="normal", family=None, bg=False, **kw):
    """Texto no tamanho de papel. bg=True põe fundo branco (pode cruzar linhas)."""
    if bg:
        kw["bbox"] = dict(fc=WHITE, ec="none", pad=0.8)
    return ax.text(x, y, s, ha=ha, va=va, fontsize=size, color=color, weight=weight, style=style,
                   family=family or SANS, zorder=4, linespacing=1.15, **kw)


def code(ax, x, y, s, size=PT_CODE, color=INK, ha="left", **kw):
    return text(ax, x, y, s, size=size, color=color, ha=ha, family=MONO, **kw)


def mark(ax, x, y, ok=True, size=10):
    return text(ax, x, y, "✓" if ok else "✗", size=size, color=(INK if ok else ACCENT), weight="bold")


# ------------------------------------------------------------------ conferência

def _segments(path, n=24):
    """Pontos de uma polilinha que aproxima o caminho (curvas amostradas)."""
    pts = path.interpolated(n).vertices if len(path.vertices) < 64 else path.vertices
    return list(zip(pts[:-1], pts[1:]))


def _seg_hits_rect(p, q, r):
    """O segmento pq cruza o retângulo r (x0, y0, x1, y1)?"""
    x0, y0, x1, y1 = r
    for t in [i / 20 for i in range(21)]:
        x = p[0] + (q[0] - p[0]) * t
        y = p[1] + (q[1] - p[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def _shrink(bb, px):
    return (bb.x0 + px, bb.y0 + px, bb.x1 - px, bb.y1 - px)


def check(f, name="figura"):
    """Lista os problemas de leitura da figura. Vazio = pode imprimir."""
    problems = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        f.canvas.draw()
    for w in caught:
        if "Glyph" in str(w.message) or "missing from" in str(w.message):
            problems.append(f"glifo sem fonte: {w.message}")
    r = f.canvas.get_renderer()
    scale = f.dpi / 72.0
    texts = [t for t in f.findobj(Text) if t.get_visible() and t.get_text().strip()
             and t.get_figure() is f and t is not getattr(f, "_suptitle", None)]
    for t in texts:
        pt = t.get_fontsize()
        if pt < MIN_PT - 1e-6:
            problems.append(f"{t.get_text()!r}: {pt:.1f} pt (mínimo {MIN_PT})")
    boxes = {id(t): t.get_window_extent(r) for t in texts}
    texts = [t for t in texts if boxes[id(t)].width > 2 and boxes[id(t)].height > 2]
    # texto contra texto
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            A, B = _shrink(boxes[id(a)], 0.2 * scale), _shrink(boxes[id(b)], 0.2 * scale)
            if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
                problems.append(f"textos encostados: {a.get_text()!r} e {b.get_text()!r}")
    for ax in f.axes:
        patches = list(ax.patches)
        lines = [ln for ln in ax.lines if ln.get_visible()]
        for t in texts:
            if t.axes is not ax:
                continue
            tb = _shrink(boxes[id(t)], 0.3 * scale)
            has_bg = t.get_bbox_patch() is not None
            for p in patches:
                if getattr(p, "_livrofig_box", False):
                    pb = p.get_window_extent(r)
                    inter = tb[0] < pb.x1 and pb.x0 < tb[2] and tb[1] < pb.y1 and pb.y0 < tb[3]
                    # dentro, com pelo menos PAD_PT de folga até o filete
                    m = PAD_PT * scale
                    inside = (pb.x0 + m <= tb[0] and tb[2] <= pb.x1 - m
                              and pb.y0 + m * 0.5 <= tb[1] and tb[3] <= pb.y1 - m * 0.5)
                    if inter and not inside and t.get_zorder() >= p.get_zorder():
                        problems.append(f"{t.get_text()!r} sai pela borda de uma caixa (ou encosta nela)")
                elif isinstance(p, FancyArrowPatch) and not has_bg:
                    path = p.get_path()
                    path = p.get_transform().transform_path(path)
                    if any(_seg_hits_rect(a, b, tb) for a, b in _segments(path)):
                        problems.append(f"{t.get_text()!r} fica em cima de uma seta (use bg=True ou mude de lugar)")
            if not has_bg:
                for ln in lines:
                    xy = ln.get_transform().transform(ln.get_xydata())
                    if any(_seg_hits_rect(a, b, tb) for a, b in zip(xy[:-1], xy[1:])):
                        problems.append(f"{t.get_text()!r} fica em cima de uma linha")
                        break
    # sem repetição
    seen, out = set(), []
    for p in problems:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def save(f, base, strict=True, png=True, svg=True):
    """Confere e grava base.svg (vetor, para o PDF) e base.png (para o ebook)."""
    problems = check(f, os.path.basename(base))
    if problems and strict:
        plt.close(f)
        raise FiguraRuim(os.path.basename(base) + ":\n  - " + "\n  - ".join(problems))
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    kw = dict(bbox_inches="tight", pad_inches=0.06)
    if svg:
        f.savefig(base + ".svg", **kw)
    if png:
        f.savefig(base + ".png", dpi=DPI_PNG, **kw)
    w_in = f.get_size_inches()[0]
    plt.close(f)
    if w_in > TEXT_W + 1e-6:
        logging.warning("%s: %.2f in, mais largo que a mancha (%.2f in)", base, w_in, TEXT_W)
    return problems


__all__ = ["setup", "canvas", "chart", "box", "arrow", "text", "code", "mark", "check", "save",
           "FiguraRuim", "INK", "GRAY", "LIGHT", "FILL", "WHITE", "SANS", "MONO", "TEXT_W", "MIN_PT",
           "PT_TITLE", "PT_LABEL", "PT_SUB", "PT_NOTE", "PT_CODE", "Circle", "Rectangle"]
