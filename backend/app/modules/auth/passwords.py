"""Validação de senhas (decisão D4: mínimo 10 + bloqueio de comuns)."""

from zxcvbn import zxcvbn

MIN_PASSWORD_LENGTH = 10
MIN_PASSWORD_SCORE = 3


class WeakPasswordError(ValueError):
    """Senha abaixo da política mínima."""


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    result = zxcvbn(password)
    if result["score"] < MIN_PASSWORD_SCORE:
        raise WeakPasswordError("A senha é muito comum ou previsível; escolha outra.")
