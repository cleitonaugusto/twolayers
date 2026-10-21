"""Formatação EFETIVA de um trecho do Word, como o programa desenha na tela.

A ordem é: padrão do documento → estilo do parágrafo → estilo do caractere → formatação direta. Ler só a formatação
direta deixa passar texto escondido por estilo e acusa letra branca que está sobre fundo escuro (visível).

Um trecho é tratado como oculto quando está marcado como oculto, tem fonte menor que 3 pt ou quando o contraste entre
a letra e o fundo fica abaixo de CONTRASTE_MINIMO. O fundo é o sombreamento ou realce do trecho, o sombreamento do
parágrafo ou, na falta deles, a cor de página do documento (branca por padrão).
"""

import re

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CONTRASTE_MINIMO = 1.5  # 1:1 = invisível; texto comum de documento fica acima de 4,5:1 (WCAG)
FONTE_MINIMA_PT = 3
REALCE = {"black": "000000", "white": "FFFFFF", "darkBlue": "00008B", "darkGray": "A9A9A9", "lightGray": "D3D3D3",
          "yellow": "FFFF00", "green": "00FF00", "cyan": "00FFFF", "blue": "0000FF", "red": "FF0000",
          "magenta": "FF00FF", "darkRed": "8B0000", "darkGreen": "006400", "darkCyan": "008B8B",
          "darkMagenta": "8B008B", "darkYellow": "808000"}


def _liga(el) -> bool | None:
    """Propriedade liga/desliga do Word: <w:vanish/> liga; <w:vanish w:val="0"/> desliga."""
    if el is None:
        return None
    return (el.get(f"{W}val") or "true").lower() not in ("0", "false", "off")


def cor(hexa: str | None) -> tuple | None:
    if not hexa or not re.fullmatch(r"[0-9A-Fa-f]{6}", hexa):
        return None  # "auto" ou ausente: o Word escolhe uma cor legível
    return tuple(int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))


def contraste(a: tuple, b: tuple) -> float:
    def lum(c):
        return sum(k * (v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
                   for k, v in zip((0.2126, 0.7152, 0.0722), c))
    claro, escuro = sorted((lum(a), lum(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def props(rpr) -> dict:
    """Só as propriedades do trecho que importam para saber se ele aparece."""
    if rpr is None:
        return {}
    d = {}
    for tag in ("vanish", "specVanish"):
        if (v := _liga(rpr.find(f"{W}{tag}"))) is not None:
            d["oculto"] = d.get("oculto") or v
    if (c := rpr.find(f"{W}color")) is not None:
        d["cor"] = c.get(f"{W}val")
    if (t := rpr.find(f"{W}sz")) is not None and (t.get(f"{W}val") or "").isdigit():
        d["tamanho_pt"] = int(t.get(f"{W}val")) / 2
    if (sh := rpr.find(f"{W}shd")) is not None and cor(sh.get(f"{W}fill")):
        d["fundo"] = sh.get(f"{W}fill")
    if (hl := rpr.find(f"{W}highlight")) is not None and hl.get(f"{W}val") in REALCE:
        d["fundo"] = REALCE[hl.get(f"{W}val")]
    return d


class Estilos:
    """styles.xml: resolve a cadeia basedOn e acumula as propriedades de cada estilo."""

    def __init__(self, raiz=None):
        self.estilos, self.padrao = {}, {}
        if raiz is None:
            return
        for st in raiz.iter(f"{W}style"):
            base = st.find(f"{W}basedOn")
            self.estilos[st.get(f"{W}styleId")] = (base.get(f"{W}val") if base is not None else None,
                                                   st.find(f"{W}rPr"), st.find(f"{W}pPr"))
        self.padrao = props(raiz.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr"))

    def do_estilo(self, sid: str | None, vistos=()) -> dict:
        if not sid or sid not in self.estilos or sid in vistos:
            return {}
        base, rpr, _ = self.estilos[sid]
        return {**self.do_estilo(base, (*vistos, sid)), **props(rpr), "estilo": sid}

    def fundo_paragrafo(self, ppr) -> str | None:
        sh = ppr.find(f"{W}shd") if ppr is not None else None
        if sh is not None and cor(sh.get(f"{W}fill")):
            return sh.get(f"{W}fill")
        ps = ppr.find(f"{W}pStyle") if ppr is not None else None
        sid, vistos = (ps.get(f"{W}val") if ps is not None else None), set()
        while sid and sid in self.estilos and sid not in vistos:
            vistos.add(sid)
            base, _, ppr_estilo = self.estilos[sid]
            sh = ppr_estilo.find(f"{W}shd") if ppr_estilo is not None else None
            if sh is not None and cor(sh.get(f"{W}fill")):
                return sh.get(f"{W}fill")
            sid = base
        return None


def motivo(efetivo: dict, papel: str | None = None) -> str:
    """Por que o trecho não aparece na leitura comum ("" = aparece)."""
    if efetivo.get("oculto"):
        return "marcado como oculto no Word" + (f" (pelo estilo {efetivo['estilo']!r})"
                                                 if efetivo.get("_oculto_por_estilo") else "")
    if efetivo.get("tamanho_pt", 99) < FONTE_MINIMA_PT:
        return f"fonte de {efetivo['tamanho_pt']:.1f} pt"
    fundo_hex = efetivo.get("fundo") or papel or "FFFFFF"
    letra, fundo = cor(efetivo.get("cor")), cor(fundo_hex)
    if letra and fundo and (k := contraste(letra, fundo)) < CONTRASTE_MINIMO:
        if min(letra) > 0.98 and min(fundo) > 0.98:
            return "texto em cor branca"
        return (f"contraste de {k:.2f}:1 entre a letra (#{efetivo['cor'].upper()}) e o fundo "
                f"(#{fundo_hex.upper()}), ilegível")
    return ""


def papel(documento) -> str | None:
    """Cor de página definida no documento (<w:background>), se houver."""
    bg = documento.find(f"{W}background") if documento is not None else None
    return bg.get(f"{W}color") if bg is not None and cor(bg.get(f"{W}color")) else None


def trechos(raiz, estilos: Estilos, cor_papel: str | None = None):
    """Para cada parágrafo da parte: (parágrafo, [(run, texto, efetivo, motivo), ...]).
    Os trechos de parágrafos aninhados (caixa de texto) saem só no parágrafo deles, nunca em dobro."""
    for par in raiz.iter(f"{W}p"):
        ppr = par.find(f"{W}pPr")
        ps = ppr.find(f"{W}pStyle") if ppr is not None else None
        base = {**estilos.padrao, **estilos.do_estilo(ps.get(f"{W}val") if ps is not None else None)}
        fundo_par = estilos.fundo_paragrafo(ppr)
        aninhados = {id(r) for p2 in par.iter(f"{W}p") if p2 is not par for r in p2.iter(f"{W}r")}
        saida = []
        for run in par.iter(f"{W}r"):
            if id(run) in aninhados:
                continue
            # texto só do próprio run (o run que contém uma caixa de texto não leva o texto dela)
            texto = "".join(t.text or "" for t in _filhos_t(run))
            if not texto:
                continue
            rpr = run.find(f"{W}rPr")
            rs = rpr.find(f"{W}rStyle") if rpr is not None else None
            direto = props(rpr)
            efetivo = {**base, **estilos.do_estilo(rs.get(f"{W}val") if rs is not None else None), **direto}
            efetivo.setdefault("fundo", fundo_par)
            if efetivo.get("fundo") is None:
                efetivo.pop("fundo")
            efetivo["_oculto_por_estilo"] = bool(efetivo.get("oculto")) and "oculto" not in direto
            saida.append((run, texto, efetivo, motivo(efetivo, cor_papel)))
        yield par, saida


def _filhos_t(run):
    """<w:t> do run, sem descer em parágrafos aninhados (caixa de texto, forma)."""
    pilha = list(run)
    while pilha:
        el = pilha.pop(0)
        if el.tag == f"{W}t":
            yield el
        elif el.tag != f"{W}p":
            pilha.extend(list(el))
