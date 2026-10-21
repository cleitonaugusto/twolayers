"""Cadeia de custódia: o registro não pode mandar conferir arquivos fora da pasta de evidências."""

from twolayers import custodia


def test_evidencia_fora_da_pasta_e_acusada(tmp_path):
    pasta = tmp_path / "evidencias"
    pasta.mkdir()
    (pasta / "peca.pdf").write_bytes(b"%PDF-1.4")
    fora = tmp_path / "segredo.txt"
    fora.write_text("x")
    reg = tmp_path / "custodia.jsonl"
    custodia.registrar(reg, "recebida", arquivo="peca.pdf", **{"sha256": custodia.hash_arquivo(pasta / "peca.pdf")["sha256"]})
    custodia.registrar(reg, "recebida", arquivo="../segredo.txt", sha256=custodia.hash_arquivo(fora)["sha256"])
    problemas = custodia.conferir(reg, pasta_evidencias=pasta)
    assert len(problemas) == 1 and "sai da pasta" in problemas[0]
