# Validação do auditar-mcp 0.15.0 (linha_do_tempo + custodia + peca)

60 casos com gabarito (6 arquivos reais de Word/Acrobat/macOS dos projetos Apache Tika e POI). Kit: auditar-mcp 0.15.0. Python 3.10.12. Corpus `8f6c13142c59c220…`. Medido em 2026-10-20T23:33:00+00:00.

| Afirmação da ferramenta | Casos | Acertos | Taxa | VP | FP | FN |
|---|---|---|---|---|---|---|
| custódia: adulteração detectada (assinada + âncora do laudo) | 6 | 6 | 100% |  |  |  |
| custódia: adulteração detectada (só encadeamento) | 6 | 4 | 67% |  |  |  |
| docx: alterações rastreadas (contagem por tipo) | 3 | 3 | 100% |  |  |  |
| docx: autores das alterações | 2 | 2 | 100% |  |  |  |
| docx: comentários | 3 | 3 | 100% |  |  |  |
| docx: sessão em que o texto entrou | 18 | 18 | 100% |  |  |  |
| docx: sessão em que o texto foi escondido | 18 | 18 | 100% |  |  |  |
| docx: texto oculto | 27 | 27 | 100% | 18 | 0 | 0 |
| pdf: comando para IA (inclusive na camada de OCR) | 2 | 2 | 100% |  |  |  |
| pdf: dados acrescentados depois do fim | 21 | 21 | 100% |  |  |  |
| pdf: número de versões salvas | 21 | 21 | 100% |  |  |  |
| pdf: texto oculto | 18 | 18 | 100% | 8 | 0 | 0 |
| pdf: versão em que o texto aparece | 2 | 2 | 100% |  |  |  |
| pdf: versão em que o texto some | 1 | 1 | 100% |  |  |  |
| verificador de peças (verificar-peca): texto oculto no Word | 27 | 27 | 100% | 18 | 0 | 0 |

VP = achou o que existe; FP = acusou o que não existe; FN = deixou passar o que existe.

## Falhas (2)

- **cu-truncada (só encadeamento)** (custódia: adulteração detectada (só encadeamento)): última linha da custódia apagada. Esperado `adulterada`, obtido `íntegra`. Lacuna conhecida: limite do encadeamento: apagar o FIM não deixa rastro sem a âncora do laudo.
- **cu-forjada-no-fim (só encadeamento)** (custódia: adulteração detectada (só encadeamento)): linha falsa acrescentada no fim, com o encadeamento recalculado. Esperado `adulterada`, obtido `íntegra`. Lacuna conhecida: limite do encadeamento: quem recalcula o hash forja o fim; só a assinatura do perito impede.
