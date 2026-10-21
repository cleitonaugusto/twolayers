"""Visibilidade medida na PÁGINA DESENHADA, como a pessoa vê (opcional: precisa do pypdfium2, o motor de PDF do Chrome).

A leitura estrutural do PDF não sabe se uma forma tem transparência nem o que um degradê desenha; por isso letra branca
sobre fundo colorido e "tarja" de marca-texto viravam falso positivo. Aqui a pergunta é feita à página: desenha-se a
página como ela é e de novo SEM os textos suspeitos; se a região da letra não muda, ninguém vê aquele texto.

Usado só para RETIRAR acusação (texto que aparece na página), nunca para criar: um ataque continua sendo pego pela
leitura estrutural, e o que a página desenhada não consegue avaliar (página girada, texto dentro de formulário
XObject) fica como estava.
"""

ESCALA = 2.0  # 144 dpi: letra de 10 pt fica com ~20 px de altura
LIMIAR_PIXEL = 40  # diferença (0–255) para um pixel contar como "mudou"
FRACAO_MINIMA = 0.02  # fração da caixa da letra que precisa mudar para a letra contar como visível


def disponivel() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


def _desenhar(pagina):
    bmp = pagina.render(scale=ESCALA)
    # conversor de coordenadas: cuida de página girada (/Rotate) e da área de corte
    return bytes(bmp.buffer), bmp.stride, bmp.width, bmp.height, bmp.n_channels, bmp.get_posconv(pagina)


MIOLO = 0.25  # margem ignorada em cada lado da caixa: a caixa do extrator tem a altura da fonte e invade a linha vizinha
INVASAO = 0.10  # fração do miolo coberta pelo desenho de OUTRA letra para a caixa ficar indecisa


def _miolo(c: tuple) -> tuple:
    mx, my = (c[2] - c[0]) * MIOLO, (c[3] - c[1]) * MIOLO
    return (c[0] + mx, c[1] + my, c[2] - mx, c[3] - my)


def _sobrepostas(pagina_texto, caixas: list[tuple], letras: list[str] | None = None) -> list[bool]:
    """Caixa em que OUTRA letra está desenhada por cima do seu miolo: há outro texto ocupando a posição da letra
    suspeita (por exemplo, uma linha visível sob ou sobre uma instrução branca). Ali, comparar a página com e sem os
    textos não diz nada sobre a letra suspeita.

    Primeiro cada caixa reconhece a própria letra no PDF (mesma letra, centro dentro da caixa); as demais letras são
    "outras". Cópia da MESMA letra no mesmo lugar (sombra, negrito simulado) não conta: o texto escondido seria igual
    ao visível."""
    from collections import defaultdict
    grade = defaultdict(list)  # célula de 20 pt -> letras que encostam nela (evita comparar todas com todas)
    chars = []
    for i in range(pagina_texto.count_chars()):
        ch = pagina_texto.get_text_range(i, 1)
        if not ch.strip():
            continue
        caixa = pagina_texto.get_charbox(i)
        k = len(chars)
        chars.append((caixa, ch.lower()))
        for gx in range(int(caixa[0] // 20), int(caixa[2] // 20) + 1):
            for gy in range(int(caixa[1] // 20), int(caixa[3] // 20) + 1):
                grade[gx, gy].append(k)

    def perto(c):
        vistos = set()
        for gx in range(int(c[0] // 20), int(c[2] // 20) + 1):
            for gy in range(int(c[1] // 20), int(c[3] // 20) + 1):
                for k in grade.get((gx, gy), ()):
                    if k not in vistos:
                        vistos.add(k)
                        yield k

    letras = [(x or "").lower() for x in (letras or [""] * len(caixas))]
    proprias = set()
    for c, letra in zip(caixas, letras):  # sem a letra (ligadura, cid), reconhece pela posição
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        candidatas = []
        for k in perto(c):
            (l, b, r, t), ch = chars[k]
            if ((not letra or ch == letra) and k not in proprias
                    and c[0] <= (l + r) / 2 <= c[2] and c[1] <= (b + t) / 2 <= c[3]):
                candidatas.append((abs((l + r) / 2 - cx) + abs((b + t) / 2 - cy), k))
        if candidatas:
            proprias.add(min(candidatas)[1])
    saida = []
    for c, letra in zip(caixas, letras):
        m = _miolo(c)
        area = max((m[2] - m[0]) * (m[3] - m[1]), 1e-9)
        invadida = False
        for k in perto(m):
            (l, b, r, t), ch = chars[k]
            if k in proprias or (letra and ch == letra):
                continue
            w, h = min(r, m[2]) - max(l, m[0]), min(t, m[3]) - max(b, m[1])
            if w > 0 and h > 0 and w * h >= INVASAO * area:
                invadida = True
                break
        saida.append(invadida)
    return saida


def visibilidade(caminho, pagina_n: int, caixas: list[tuple], letras: list[str] | None = None) -> list[bool | None]:
    """Para cada caixa (x0, y0, x1, y1, em pontos do PDF): True = o texto ali aparece na página desenhada; False = não
    aparece; None = não deu para avaliar.

    Caixa onde outra letra ocupa o mesmo lugar (uma linha visível sob ou sobre o texto escondido) fica None: removendo
    os objetos de texto, a linha visível sairia junto, a região mudaria e o texto escondido pareceria visível.
    letras: a letra suspeita de cada caixa (opcional), para não confundir sombra ou negrito simulado com sobreposição."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    if not caixas:
        return []
    original = pdfium.PdfDocument(str(caminho))
    sem_texto = pdfium.PdfDocument(str(caminho))
    pa = pb = None
    try:
        pa, pb = original[pagina_n - 1], sem_texto[pagina_n - 1]

        def toca(o, c):  # objeto de texto (limites em pontos) cruza a caixa da letra?
            l, b, r, t = o
            return not (r <= c[0] or l >= c[2] or t <= c[1] or b >= c[3])

        alcancadas = [False] * len(caixas)
        pagina_texto = pa.get_textpage()
        try:
            ambiguas = _sobrepostas(pagina_texto, caixas, letras)
        finally:
            pagina_texto.close()
        removidos = []
        for obj in list(pb.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT], max_depth=1)):
            limites = obj.get_bounds()
            atinge = [i for i, c in enumerate(caixas) if toca(limites, c)]
            if not atinge:
                obj.close()
                continue
            pb.remove_obj(obj)
            removidos.append(obj)
            for i in atinge:
                alcancadas[i] = True
        if not removidos:
            return [None] * len(caixas)
        pb.gen_content()
        for obj in removidos:  # objeto removido da página fica solto: fechar aqui libera a memória do PDFium
            obj.close()
        a, stride, largura, altura, canais, conv = _desenhar(pa)
        b, stride_b, *_ = _desenhar(pb)
        if stride_b != stride:
            return [None] * len(caixas)

        resultado = []
        for c, alcancada, ambigua in zip(caixas, alcancadas, ambiguas):
            if not alcancada or ambigua:
                resultado.append(None)
                continue
            m = _miolo(c)  # só o miolo: a tinta de uma letra vizinha removida não pode contar como "aparece"
            cantos = [conv.to_bitmap(x, y) for x in (m[0], m[2]) for y in (m[1], m[3])]
            x0 = max(0, int(min(p[0] for p in cantos)))
            x1 = min(largura, int(max(p[0] for p in cantos)) + 1)
            y0 = max(0, int(min(p[1] for p in cantos)))
            y1 = min(altura, int(max(p[1] for p in cantos)) + 1)
            total = mudou = 0
            for y in range(y0, y1):
                linha = y * stride
                for x in range(x0, x1):
                    p = linha + x * canais
                    total += 1
                    if max(abs(a[p + k] - b[p + k]) for k in range(min(canais, 3))) > LIMIAR_PIXEL:
                        mudou += 1
            resultado.append(None if not total else mudou >= max(2, FRACAO_MINIMA * total))
        return resultado
    finally:  # páginas antes dos documentos (o pypdfium2 exige essa ordem)
        for pg in (pa, pb):
            if pg is not None:
                pg.close()
        original.close()
        sem_texto.close()
