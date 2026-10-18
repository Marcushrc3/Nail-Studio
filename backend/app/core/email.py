"""Interface de envio de e-mail, desacoplada do fornecedor (E1.2).

Os fluxos de cadastro/verificação dependem apenas de ``EmailProvider``.
Na E1.4 entra o adaptador SMTP (Gmail) selecionado por configuração;
nesta etapa existe somente o provedor falso, que NUNCA envia de verdade.
"""

from __future__ import annotations

from typing import Protocol


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, text_body: str) -> None: ...


class FakeEmailProvider:
    """Registra os envios em memória para inspeção nos testes."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, text_body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text_body": text_body})


_fake_singleton = FakeEmailProvider()


def get_email_provider() -> EmailProvider:
    """Dependência FastAPI do provedor de e-mail.

    E1.4: passará a escolher SMTP quando ``EMAIL_PROVIDER=smtp``.
    """
    return _fake_singleton
