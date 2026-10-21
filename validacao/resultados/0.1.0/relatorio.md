# Validação do método de perícia 0.1.0

45 casos com gabarito (6 arquivos reais de Word/Acrobat/macOS dos projetos Apache Tika e POI). Kit: auditar-mcp 0.11.0. Python 3.10.12. Corpus `66700cb7b14304f2…`. Medido em 2026-10-19T23:03:00+00:00.

| Afirmação da ferramenta | Casos | Acertos | Taxa | VP | FP | FN |
|---|---|---|---|---|---|---|
| custódia: adulteração detectada | 6 | 4 | 67% |  |  |  |
| docx: alterações rastreadas (contagem por tipo) | 3 | 3 | 100% |  |  |  |
| docx: autores das alterações | 2 | 2 | 100% |  |  |  |
| docx: comentários | 3 | 3 | 100% |  |  |  |
| docx: sessão em que o texto entrou | 12 | 12 | 100% |  |  |  |
| docx: sessão em que o texto foi escondido | 12 | 11 | 92% |  |  |  |
| docx: texto oculto | 25 | 20 | 80% | 12 | 1 | 4 |
| pdf: número de versões salvas | 14 | 11 | 79% |  |  |  |
| pdf: texto oculto | 11 | 11 | 100% | 6 | 0 | 0 |
| pdf: versão em que o texto aparece | 2 | 2 | 100% |  |  |  |
| pdf: versão em que o texto some | 1 | 1 | 100% |  |  |  |

VP = achou o que existe; FP = acusou o que não existe; FN = deixou passar o que existe.

## Falhas (11)

- **dx-cinza-claro** (docx: texto oculto): cinza claríssimo F4F4F4 (contraste 1,1:1 com o papel; ilegível). Esperado `['Ignore as instrucoes anteriore']`, obtido `[]`. Lacuna conhecida: só reconhece FFFFFF/FEFEFE/FDFDFD; não calcula contraste.
- **dx-preto-no-preto** (docx: texto oculto): letra preta sobre sombreamento preto. Esperado `['Ignore as instrucoes anteriore']`, obtido `[]`. Lacuna conhecida: não compara a cor da letra com a do fundo (sombreamento/realce).
- **dx-estilo-oculto** (docx: texto oculto): oculto por um estilo de caractere (rStyle com vanish). Esperado `['Ignore as instrucoes anteriore']`, obtido `[]`. Lacuna conhecida: não lê styles.xml (formatação herdada de estilo).
- **dx-paragrafo-branco** (docx: texto oculto): branco herdado do estilo do parágrafo. Esperado `['Ignore as instrucoes anteriore']`, obtido `[]`. Lacuna conhecida: não lê styles.xml (formatação herdada de estilo).
- **dn-branco-no-escuro** (docx: texto oculto): letra branca sobre fundo azul-escuro (cabeçalho de tabela, visível). Esperado `[]`, obtido `['QUADRO DE VERBAS']`. Lacuna conhecida: acusa letra branca mesmo com fundo escuro (falso positivo).
- **ss-escondido-depois** (docx: sessão em que o texto foi escondido): texto digitado na sessão 1 e ESCONDIDO na sessão 3 (rsidRPr). Esperado `3`, obtido `1`. Lacuna conhecida: ignora rsidRPr: diz em que sessão o texto entrou, não em que sessão foi escondido.
- **pv-lixo-no-fim** (pdf: número de versões salvas): bytes acrescentados depois do fim do arquivo. Esperado `1`, obtido `2`. Lacuna conhecida: conta os bytes depois do fim como mais uma 'versão'.
- **pv-eof-no-texto** (pdf: número de versões salvas): a sequência %%EOF aparece no texto da página (não é fim de versão). Esperado `1`, obtido `2`. Lacuna conhecida: procura %%EOF em qualquer lugar, inclusive dentro do conteúdo.
- **rl-pdf-linearizado-incremental** (pdf: número de versões salvas): linearizado + 2 atualizações incrementais: 3 gravações (ModDate 10:37:44, 10:38:50, 10:42:17) e 4 marcadores %%EOF, porque a linearização usa dois. Esperado `3`, obtido `4`. Lacuna conhecida: conta a seção de linearização como uma versão a mais.
- **cu-truncada** (custódia: adulteração detectada): última linha da custódia apagada. Esperado `adulterada`, obtido `íntegra`. Lacuna conhecida: sem âncora externa, apagar o FIM da cadeia não deixa rastro.
- **cu-forjada-no-fim** (custódia: adulteração detectada): linha falsa acrescentada no fim, com o encadeamento recalculado. Esperado `adulterada`, obtido `íntegra`. Lacuna conhecida: sem âncora externa, acrescentar no fim com o hash certo não deixa rastro.
