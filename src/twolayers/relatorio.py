"""Relatório HTML autocontido (um arquivo, sem dependências externas), pronto para entregar ao cliente."""

from datetime import datetime
from html import escape

from . import __version__
from .achados import NA, OK, REVISAR, RISCO

ORDEM = {RISCO: 0, REVISAR: 1, OK: 2, NA: 3}
SEV = {"A": 0, "M": 1, "B": 2}
NOME_SEV = {"A": "Alta", "M": "Média", "B": "Baixa"}

CSS = """
:root{--fundo:#f7f7f5;--papel:#fff;--texto:#1d1d1f;--suave:#6b6b70;--linha:#e3e3e0;
--risco:#b42318;--risco-f:#fef3f2;--revisar:#b54708;--revisar-f:#fffaeb;--ok:#067647;--ok-f:#ecfdf3;--na:#6b6b70;--na-f:#f2f2f0}
@media (prefers-color-scheme:dark){:root{--fundo:#141416;--papel:#1d1d20;--texto:#ececee;--suave:#a0a0a8;--linha:#33333a;
--risco:#f97066;--risco-f:#3a1715;--revisar:#fdb022;--revisar-f:#3a2a0c;--ok:#47cd89;--ok-f:#0f2e1f;--na:#a0a0a8;--na-f:#26262b}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--suave);margin:0 0 24px;word-break:break-all}
.cartoes{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.cartao{background:var(--papel);border:1px solid var(--linha);border-radius:10px;padding:14px 16px}
.cartao b{display:block;font-size:28px;line-height:1.1}.cartao span{color:var(--suave);font-size:13px}
.item{background:var(--papel);border:1px solid var(--linha);border-left-width:4px;border-radius:8px;margin:0 0 10px;padding:12px 16px}
.item.RISCO{border-left-color:var(--risco)}.item.REVISAR{border-left-color:var(--revisar)}
.item.OK{border-left-color:var(--ok)}.item.NA{border-left-color:var(--na)}
.cab{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.selo{font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px}
.selo.RISCO{color:var(--risco);background:var(--risco-f)}.selo.REVISAR{color:var(--revisar);background:var(--revisar-f)}
.selo.OK{color:var(--ok);background:var(--ok-f)}.selo.NA{color:var(--na);background:var(--na-f)}
.num{color:var(--suave);font-variant-numeric:tabular-nums}.tit{font-weight:600}
ul{margin:8px 0 0;padding-left:20px}li{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-word;color:var(--suave)}
table{width:100%;border-collapse:collapse;background:var(--papel);border:1px solid var(--linha);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--linha);font-size:14px}
td code{font-size:13px}.rodape{color:var(--suave);font-size:13px;margin-top:40px}
@media print{body{background:#fff}.item,.cartao,table{break-inside:avoid}}
"""


def _classe(resultado: str) -> str:
    return "NA" if resultado == NA else resultado


NOTA_PECA = ("A verificação é local: o documento não saiu do computador. Número com dígito válido e súmula com número "
             "plausível não provam que o precedente existe nem que diz o que foi citado — confira cada um no site do tribunal.")


def gerar(achados, ferramentas, alvo: str, cliente: str | None = None,
          titulo: str = "Relatório", nota: str = NOTA_PECA, cartoes: list | None = None,
          notas_extras: list | None = None) -> str:
    cont = {r: sum(a.resultado == r for a in achados) for r in (RISCO, REVISAR, OK, NA)}
    altos = sum(a.resultado == RISCO and a.sev == "A" for a in achados)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    partes = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{escape(titulo)}</title><style>{CSS}</style></head><body><main>",
        f"<h1>{escape(titulo)}</h1>",
        f"<p class='sub'>{escape(cliente + ' · ') if cliente else ''}Alvo: {escape(alvo)} · {agora}</p>",
        "<div class='cartoes'>",
        f"<div class='cartao'><b style='color:var(--risco)'>{cont[RISCO]}</b><span>riscos ({altos} de severidade alta)</span></div>",
        f"<div class='cartao'><b style='color:var(--revisar)'>{cont[REVISAR]}</b><span>a revisar</span></div>",
        f"<div class='cartao'><b style='color:var(--ok)'>{cont[OK]}</b><span>ok</span></div>",
        *[f"<div class='cartao'><b>{escape(str(v))}</b><span>{escape(r)}</span></div>"
          for v, r in (cartoes if cartoes is not None else [(len(ferramentas), "ferramentas expostas")])],
        "</div>",
        "<h2>Itens verificados</h2>",
    ]
    for a in sorted(achados, key=lambda a: (ORDEM[a.resultado], SEV[a.sev], a.item)):
        c = _classe(a.resultado)
        partes.append(f"<div class='item {c}'><div class='cab'><span class='selo {c}'>{escape(a.resultado)}</span>"
                      f"<span class='num'>{escape(a.item)} · severidade {NOME_SEV[a.sev].lower()}</span>"
                      f"<span class='tit'>{escape(a.titulo)}</span></div>")
        if a.evidencias:
            partes.append("<ul>" + "".join(f"<li>{escape(e)}</li>" for e in a.evidencias[:30]) + "</ul>")
            if len(a.evidencias) > 30:
                partes.append(f"<p class='num'>… e mais {len(a.evidencias) - 30}</p>")
        partes.append("</div>")
    if ferramentas:
        partes.append("<h2>Ferramentas expostas ao modelo</h2><table><tr><th>ferramenta</th><th>local</th><th>hash da descrição</th></tr>")
        partes += [f"<tr><td>{escape(t['nome'])}</td><td><code>{escape(t['local'])}</code></td><td><code>{escape(t['hash'])}</code></td></tr>"
                   for t in ferramentas]
        partes.append("</table>")
    partes += [
        "<h2>Como ler</h2>",
        "<p><b>RISCO</b>: problema encontrado, corrigir. <b>REVISAR</b>: ponto que exige olhar humano (a análise automática "
        f"indica onde olhar, não conclui). <b>OK</b>: nada encontrado pela verificação automática. {escape(nota)}</p>",
        *(f"<p>{escape(n)}</p>" for n in (notas_extras or [])),
        f"<p class='rodape'>twolayers {__version__}</p></main></body></html>",
    ]
    return "\n".join(partes)
