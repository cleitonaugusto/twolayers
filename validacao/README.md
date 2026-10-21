# Validação do método de perícia de documentos

Um método pericial só é aceito quando se sabe **quando ele erra**. Esta pasta mede cada afirmação que o kit faz sobre
um documento, em três níveis, e guarda o resultado de cada rodada. Os módulos medidos são `peca` (verificador de
peças), `formatacao`, `render` (página desenhada), `linha_do_tempo` (sessões do Word, versões do PDF) e `custodia`.

```bash
python3 validacao/medir.py --saida validacao/resultados/<versão>        # nível 1: gabarito
python3 validacao/volume.py <pasta com documentos> --saida resultado.json  # nível 2: volume, sem gabarito
```

## Nível 1 — gabarito

- **Sintético** (`casos.py`): documentos montados byte a byte para isolar uma técnica de cada vez, tanto as de
  esconder (letra branca, quase branca, preta sobre fundo preto, oculto por estilo, fonte de 1 pt, cabeçalho, nota,
  caixa de texto, controle de conteúdo, corretivo branco e retângulo claro opaco por cima, instrução dentro da camada
  de OCR) quanto as **armadilhas** (letra branca sobre fundo escuro, marca-texto transparente, `%%EOF` dentro do texto,
  página digitalizada, letras soltas minúsculas, letra branca na mesma posição de uma linha visível).
- **Real**: arquivos de teste públicos dos projetos Apache Tika e POI, criados por Word, Acrobat e macOS de verdade.
  O gabarito foi levantado **à mão, no XML e nos bytes, sem rodar a ferramenta** (senão seria circular), e o SHA-256 de
  cada arquivo fica fixado em `casos.py`. Para incluí-los, baixe dos repositórios de teste do Apache Tika e do Apache POI
  os arquivos abaixo, mantendo as subpastas, e aponte `AUDITAR_CORPUS_REAL` para a pasta (padrão:
  `validacao/corpus-real/`). Sem eles, os casos reais são pulados e o resto continua valendo.
  - `tika/testPDF_incrementalUpdates.pdf`, `tika/testComment.pdf`, `tika/testPDF.pdf`
  - `tika/testComment.docx`, `tika/testWORD.docx`, `poi/delins.docx`
- **Custódia**: seis adulterações (byte da evidência, linha editada, apagada no meio, apagada no fim, forjada no fim),
  em dois modos: só o encadeamento por hash, e com cada linha assinada pelo examinador mais a âncora do relatório.

Cada relatório registra a versão do kit, o Python e o **hash do corpus**; os documentos gerados têm data fixa, então o
mesmo corpus dá os mesmos bytes em qualquer máquina. O teste `tests/test_validacao.py` falha se alguma taxa cair abaixo
da última linha de base (`resultados/kit-0.18.0`) ou se aparecer uma falha fora das lacunas conhecidas.

Resultado atual (61 casos, 6 reais): todas as afirmações acertam 100% do corpus, exceto a custódia **só com
encadeamento** (4/6), mantida de propósito: sem assinatura e âncora, apagar ou forjar o fim do registro não deixa
rastro. Com assinatura e âncora, 6/6.

Evolução registrada em `resultados/0.1.0` e `resultados/0.2.0`: texto oculto no Word 80% → 100%; sessão em que o texto
foi escondido 92% → 100%; número de versões do PDF 79% → 100%. Um arquivo real do Tika foi salvo **3 vezes** mas tem
**4** marcadores `%%EOF` (é linearizado): a contagem ingênua inventaria uma versão. Uma previsão errada fica registrada:
supôs-se que o verificador acusaria letra branca sobre faixa escura, e ele já considerava o fundo.

## Nível 2 — volume (Govdocs1)

Quanto a ferramenta acusa em documentos comuns: as duas primeiras partes do Govdocs1 (digitalcorpora.org), 683
arquivos reais de sites do governo dos EUA. `volume.py` usa um processo por arquivo, encerrado à força em 60 s.
Resumos de cada rodada em `resultados/volume-govdocs1/`.

| Rodada | PDFs lidos | Com algum alerta | Texto oculto | Travou |
|---|---|---|---|---|
| 1. kit 0.12 | 480 | 225 (47%) | 189 (39%) | 4 |
| 2. OCR, branco sobre imagem, fragmentos | 479 | 160 (33%) | 117 (24%) | 5 |
| 3. tarja cobrindo a letra, palavra de 3 letras, < 2 pt | 473 | 145 (31%) | 102 (22%) | 11 |
| 4. verificação de cobertura reescrita | 480 | 147 (31%) | 103 (21%) | 4 |
| 5. página desenhada, páginas giradas | 481 | 120 (25%) | 75 (16%) | 3 |
| 6. escaneado em recortes, área de corte (CropBox) | 479 | 119 (25%) | 74 (15%) | 5 |
| 7. brecha da revisão fechada (1ª correção, por texto do objeto) | 479 | 130 (27%) | 86 (18%) | 5 |
| 8. sobreposição decidida pela geometria (kit 0.16.0) | 479 | 122 (25%) | 77 (16%) | 5 |

O que a medição mudou: `.doc`, `.odt` e `.rtf` passaram a ser **recusados** (eram lidos como texto e geravam lixo);
a camada de OCR de página digitalizada deixou de ser "texto oculto", mas continua passando pela busca de instruções
para IA; letras soltas, rótulos de mapa, bordas de tabela e marca-texto deixaram de ser acusados; a página desenhada
fechou uma brecha (retângulo claro **opaco** por cima de uma instrução).

**Brecha achada na revisão de código (rodadas 7 e 8).** A conferência na página desenhada removia *todos* os objetos de
texto que encostavam no trecho suspeito. Uma instrução em letra branca escrita na mesma posição de uma linha visível
saía junto com a linha, a região mudava e a instrução era dada como visível: o ataque passava sem acusação. A 1ª
correção (rodada 7) só removia objetos cujo texto fosse o trecho suspeito; fechou a brecha, mas a verificação
independente achou **8 acusações erradas** novas (objetos que misturam o trecho suspeito com letras vizinhas). A
correção final (rodada 8) decide pela geometria: a caixa da letra suspeita fica indecisa só se o desenho de **outra**
letra cobre o seu miolo; a comparação de pixels usa só o miolo; e a acusação sai pela maioria das letras avaliadas,
desde que sejam ao menos 3 e um quarto do trecho. Caso no gabarito: `po-branco-sobreposto`; testes nas duas ordens de
desenho e com sombra branca do mesmo texto.

## Nível 3 — verificação independente (`segundo-avaliador/`)

Sem avaliador humano: cada acusação de uma rodada é conferida por **outro** motor de PDF (Poppler, só a área de corte,
300 dpi) e por OCR (Tesseract), calibrado com um trecho visível de controle da mesma página.

Os trechos que o OCR acha mas que também existem como **cópia visível** na mesma página (por exemplo, título duplicado
escondido) são inconclusivos; isso é decidido pelo script (`copia_visivel`), não à mão.

| Rodada | Controles visíveis achados pelo OCR | Trecho acusado NÃO aparece | Inconclusivos | Acusação errada |
|---|---|---|---|---|
| 6 | 59/66 (89%) | 60/71 (85%) | 11 | 0 |
| 7 (1ª correção) | 69/77 (90%) | 64/83 (77%) | 11 | **8** |
| 8, regra só por semelhança | 62/69 (90%) | 63/74 (85%) | 10 | 1 |
| 8, regra com ordem das palavras | 61/69 (88%) | 65/74 (88%; IC95% 79–94%) | 9 | **0** |

A única "errada" da regra só por semelhança era erro do verificador: o OCR leu "55 system summary" (número da página +
título) e a regra aceitou como a legenda escondida "Table 1. System Summary.". A regra com ordem das palavras
(`OCR_REGRA`, padrão) vale também para os controles; os dois resultados ficam em `segundo-avaliador/rodada8/`. Na
rodada 5, a verificação achou um erro real (página escaneada em recortes), corrigido antes da rodada 6. A rodada 6
usou a classificação de cópia visível feita à mão (`duplicados.json`), substituída pelo script.

`gerar.py` monta, a partir de uma rodada, um pacote para avaliação **humana** às cegas (PDFs renomeados por código e
planilha com lista de respostas), caso uma revisão peça.

## Benchmark externo, a frio (CrackedPDFs)

`crackedpdfs.py`, `crackedpdfs_ocultos.py` e `crackedpdfs_semantico.py` avaliam o kit, **sem treino nem ajuste**, no
split de teste do benchmark público CrackedPDFs (Thienpreecha e Subramanian, 2026; 2.919 PDFs em trios: benigno,
benigno com a mesma estrutura escondendo texto benigno, injetado). Resultados em `resultados/crackedpdfs/`:

- **localizar conteúdo escondido**: 93% dos PDFs injetados (14 de 15 famílias), nenhum benigno original acusado
  (igual com o kit 0.16.0, depois da correção da brecha: `metricas-kit-0.18.0.json`);
- **julgar intenção**: fraco neste benchmark (instruções em inglês; a camada de intenção é calibrada em português);
  o kit acusa igualmente os benignos que escondem texto da mesma forma, porque relata *o que está escondido*, não
  *por quê*.

## Limites

- O corpus com gabarito é pequeno (60 casos) e cobre DOCX e PDF; faltam e-mail (EML/MSG), ODT, DOC binário e PDF com
  assinatura digital (alterações depois de assinar).
- O corpus de volume é de documentos governamentais de 2009, não de peças jurídicas.
- 100% aqui quer dizer "acerta todos os casos **deste** corpus", não "nunca erra". Cada lacuna nova entra primeiro como
  caso que falha e só depois como correção.
