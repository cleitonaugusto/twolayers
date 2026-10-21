"""Registro de cadeia de custódia (implementação de referência).

Um arquivo JSON Lines em que cada linha leva o hash da anterior (encadeamento) e, se houver chave, a assinatura
Ed25519 do examinador. O relatório entregue registra uma ÂNCORA (número de linhas e hash da última).

Por que as três coisas: o encadeamento sozinho pega edição e remoção no MEIO, mas não pega quem apaga o FIM nem quem
acrescenta no fim recalculando os hashes. A assinatura impede linha forjada (quem forja não tem a chave privada); a
âncora no relatório já entregue impede apagar o fim.

Linhas com "arquivo" e "sha256" referenciam evidências: conferir() verifica se o arquivo ainda tem o mesmo hash.
A assinatura precisa do pacote `cryptography`; sem chave, o registro funciona só com o encadeamento.
"""

import base64
import getpass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def agora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def hash_arquivo(caminho: Path) -> dict:
    h256, h512 = hashlib.sha256(), hashlib.sha512()
    with Path(caminho).open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h256.update(bloco)
            h512.update(bloco)
    return {"sha256": h256.hexdigest(), "sha512": h512.hexdigest(), "bytes": Path(caminho).stat().st_size}


def hash_linha(linha: dict) -> str:
    return hashlib.sha256(json.dumps(linha, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(t: str) -> bytes:
    return base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))


def impressao(publica: bytes) -> str:
    """Impressão digital da chave pública (vai no relatório)."""
    return hashlib.sha256(publica).hexdigest()[:16]


def gerar_chave(destino: Path) -> str:
    """Cria o par Ed25519: a privada em `destino` (permissão 600), a pública em `destino`.pub. Devolve a impressão."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    destino = Path(destino)
    if destino.exists():
        raise FileExistsError(f"já existe uma chave em {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    privada = Ed25519PrivateKey.generate()
    destino.write_bytes(privada.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    destino.chmod(0o600)
    publica = privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    destino.with_suffix(".pub").write_text(_b64(publica) + "\n")
    return impressao(publica)


def carregar_privada(caminho: Path | None):
    if caminho is None or not Path(caminho).exists():
        return None
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(Path(caminho).read_bytes(), password=None)


def carregar_publica(caminho: Path | None) -> bytes | None:
    return _unb64(Path(caminho).read_text().strip()) if caminho and Path(caminho).exists() else None


def ler(registro: Path) -> list[dict]:
    registro = Path(registro)
    return ([json.loads(l) for l in registro.read_text(encoding="utf-8").splitlines() if l.strip()]
            if registro.exists() else [])


def registrar(registro: Path, evento: str, privada=None, **dados) -> dict:
    """Acrescenta uma linha. privada: chave carregada com carregar_privada() (ou None: só encadeamento)."""
    linhas = ler(registro)
    linha = {"n": len(linhas) + 1, "quando": agora(), "evento": evento,
             "por": dados.pop("por", None) or getpass.getuser(), **dados,
             "anterior": hash_linha(linhas[-1]) if linhas else None}
    if privada is not None:
        from cryptography.hazmat.primitives import serialization
        pub = privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        linha["chave"] = impressao(pub)
        linha["assinatura"] = _b64(privada.sign(_canon(linha)))
    with Path(registro).open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


def ancora(registro: Path) -> dict:
    """O que o relatório registra para fixar a cadeia: quantas linhas havia e o hash da última."""
    linhas = ler(registro)
    return {"linhas": len(linhas), "hash_ultima": hash_linha(linhas[-1]) if linhas else None}


def conferir(registro: Path, publica: bytes | None = None, ancora_relatorio: dict | None = None,
             pasta_evidencias: Path | None = None) -> list[str]:
    """Problemas encontrados (vazio = íntegro). publica: chave do examinador vinda de fonte confiável (não do próprio
    registro); ancora_relatorio: {"linhas", "hash_ultima"} de um relatório já entregue; pasta_evidencias: onde estão
    os arquivos citados nas linhas com "arquivo" e "sha256"."""
    problemas = []
    linhas = ler(registro)
    for i, linha in enumerate(linhas):
        esperado = hash_linha(linhas[i - 1]) if i else None
        if linha.get("anterior") != esperado or linha.get("n") != i + 1:
            problemas.append(f"linha {i + 1} não encadeia com a anterior (editada, apagada ou inserida)")
    if publica is not None:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        chave = Ed25519PublicKey.from_public_bytes(publica)
        for linha in linhas:
            corpo = {k: v for k, v in linha.items() if k != "assinatura"}
            try:
                chave.verify(_unb64(linha.get("assinatura", "")), _canon(corpo))
            except (InvalidSignature, ValueError):
                problemas.append(f"linha {linha.get('n')} sem assinatura válida da chave {impressao(publica)}")
    if ancora_relatorio:
        n, h = ancora_relatorio["linhas"], ancora_relatorio["hash_ultima"]
        if len(linhas) < n:
            problemas.append(f"o relatório registrou {n} linhas e agora há {len(linhas)}: linhas apagadas")
        elif n and hash_linha(linhas[n - 1]) != h:
            problemas.append(f"a linha {n} não é a que o relatório registrou (hash diferente)")
    if pasta_evidencias is not None:
        for linha in linhas:
            if "arquivo" in linha and "sha256" in linha:
                base = Path(pasta_evidencias).resolve()
                arq = (base / linha["arquivo"]).resolve()
                rotulo = linha.get("id", linha["arquivo"])
                if not arq.is_relative_to(base):  # o registro não pode apontar para fora da pasta de evidências
                    problemas.append(f"{rotulo}: caminho da evidência sai da pasta ({linha['arquivo']})")
                elif not arq.exists():
                    problemas.append(f"{rotulo}: arquivo da evidência sumiu ({linha['arquivo']})")
                elif hash_arquivo(arq)["sha256"] != linha["sha256"]:
                    problemas.append(f"{rotulo}: SHA-256 diferente do registrado: evidência alterada")
    return problemas
