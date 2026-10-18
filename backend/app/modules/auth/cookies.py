"""Cookies do refresh token (HttpOnly, SameSite=Lax, Secure em produção)."""

from fastapi import Request, Response

COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(
    response: Response, raw_token: str, *, max_age_seconds: int, secure: bool
) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
        max_age=max_age_seconds,
    )


def clear_refresh_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
    )


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)
