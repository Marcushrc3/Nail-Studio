"""Política de senha (D4: mínimo 10 + bloqueio de senhas comuns)."""

import pytest

from app.modules.auth.passwords import WeakPasswordError, validate_password_strength


def test_accepts_strong_password() -> None:
    validate_password_strength("UmaSenhaMuitoForte@2026")


def test_rejects_short_password() -> None:
    with pytest.raises(WeakPasswordError, match="10 caracteres"):
        validate_password_strength("Abc@12345")


def test_rejects_numeric_sequence() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("123456789012345")


def test_rejects_common_password() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("password123")
