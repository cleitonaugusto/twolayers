"""Checagem antes de enviar: o resultado do verificar-peca em linguagem de escritório.

Três veredictos, nunca "pode protocolar" (a ferramenta não tem como garantir isso):
  CORRIJA ANTES DE ENVIAR   há risco encontrado
  CONFIRA ANTES DE ENVIAR   não há risco, mas há pontos que só uma pessoa pode confirmar
  NADA ENCONTRADO           as verificações automáticas não acharam nada (não substitui a revisão)
"""

from .achados import REVISAR, RISCO, Achado

CORRIJA, CONFIRA, NADA = "CORRIJA ANTES DE ENVIAR", "CONFIRA ANTES DE ENVIAR", "NADA ENCONTRADO"

# primeiro o que leva a multa (recado escondido para IA), depois o que vaza sigilo, por último as citações
PRIORIDADE = ["T3", "T1", "T2", "V1", "V2", "V4", "V3", "V5", "C1", "C2", "C3"]

# o que fazer, por item, quando há RISCO
CORRIGIR = {
    "T1": "Há texto escondido no arquivo (letra branca, minúscula, fora da página ou coberta). Apague-o no documento "
          "original e gere o PDF de novo. Tarja desenhada não apaga o texto que está embaixo.",
    "T2": "Há caracteres invisíveis usados para esconder conteúdo. Cole o texto num editor simples, ou refaça o trecho "
          "digitando de novo.",
    "T3": "Há frase dirigida a uma inteligência artificial. Remova-a: tribunais já multam quem assina a peça, mesmo "
          "quando o texto veio de um modelo ou de terceiro.",
    "C1": "Há número de processo que não pode existir (dígito verificador errado). Confira o número correto.",
    "C2": "Há súmula com número que não existe. Confira a citação.",
    "V1": "Há alterações rastreadas: o texto apagado continua dentro do arquivo. No Word, aceite ou rejeite todas as "
          "alterações (guia Revisão) antes de salvar e gerar o PDF.",
    "V2": "Há comentários internos no arquivo (ou impressos na margem do PDF). Exclua todos os comentários e exporte o "
          "PDF sem marcações.",
    "V3": "Os metadados guardam caminhos internos (pasta, servidor ou modelo de origem). Use o inspetor de documento do "
          "Word (Arquivo → Informações → Verificar se há problemas) para remover propriedades e informações pessoais.",
    "V4": "O PDF guarda uma versão anterior com texto que não está na versão final. Gere o PDF de novo a partir do "
          "documento original, em vez de editar o PDF pronto.",
    "V5": "O arquivo tem conteúdo ativo (macro, JavaScript ou modelo baixado da internet ao abrir). Salve uma cópia "
          "limpa (.docx sem macros, ou PDF gerado de novo).",
}

# o que conferir, por item, quando o resultado é REVISAR
CONFERIR = {
    "T2": "Há caracteres invisíveis comuns em texto copiado de sites. Confira se não alteram o sentido.",
    "C1": "Os números de processo têm formato válido, mas a existência não foi verificada: confira no tribunal.",
    "C2": "Confira o enunciado das súmulas citadas.",
    "C3": "Confira cada precedente citado no site do tribunal (número, relator, ementa).",
    "V1": "Há inserções rastreadas ainda não aceitas. Aceite-as antes de enviar.",
    "V3": "O arquivo leva autor, título ou empresa nos metadados. Confira se essas informações podem sair do escritório.",
    "V5": "O arquivo tem arquivos embutidos ou vínculos externos. Confira se devem ir junto.",
}


def parecer(achados: list[Achado]) -> tuple[str, list[str], list[str]]:
    """Veredicto, lista do que corrigir e lista do que conferir (cada item com o primeiro exemplo encontrado)."""
    corrigir, conferir = [], []
    for a in sorted(achados, key=lambda a: PRIORIDADE.index(a.item) if a.item in PRIORIDADE else 99):
        exemplo = f" Exemplo: {a.evidencias[0]}" if a.evidencias else ""
        if a.resultado == RISCO and a.item in CORRIGIR:
            corrigir.append(CORRIGIR[a.item] + exemplo)
        elif a.resultado == REVISAR and a.item in CONFERIR:
            conferir.append(CONFERIR[a.item] + exemplo)
    veredicto = CORRIJA if corrigir else (CONFIRA if conferir else NADA)
    return veredicto, corrigir, conferir


def texto(nome: str, achados: list[Achado]) -> str:
    veredicto, corrigir, conferir = parecer(achados)
    linhas = [f"{nome}: {veredicto}", ""]
    if corrigir:
        linhas.append("Corrija:")
        linhas += [f"  {i}. {t}" for i, t in enumerate(corrigir, 1)]
        linhas.append("")
    if conferir:
        linhas.append("Confira:")
        linhas += [f"  {i}. {t}" for i, t in enumerate(conferir, 1)]
        linhas.append("")
    linhas.append("Verificação automática, feita neste computador. Ela aponta onde olhar; não substitui a revisão.")
    return "\n".join(linhas)
