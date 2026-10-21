"""Resultado de cada verificação: item, severidade, resultado e evidências."""

from dataclasses import dataclass, field

OK, RISCO, REVISAR, NA = "OK", "RISCO", "REVISAR", "N/A"


@dataclass
class Achado:
    item: str
    sev: str
    resultado: str
    titulo: str
    evidencias: list = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"item": self.item, "sev": self.sev, "resultado": self.resultado,
                "titulo": self.titulo, "evidencias": self.evidencias}
