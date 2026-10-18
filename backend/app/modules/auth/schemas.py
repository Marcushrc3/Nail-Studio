"""Schemas de entrada/saída do módulo de autenticação."""

from pydantic import BaseModel, EmailStr, Field

MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 100


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = Field(min_length=MIN_NAME_LENGTH, max_length=MAX_NAME_LENGTH)
    phone: str | None = None
    timezone: str = "America/Sao_Paulo"
    terms_version: str = Field(min_length=1, max_length=50)
    privacy_version: str = Field(min_length=1, max_length=50)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
