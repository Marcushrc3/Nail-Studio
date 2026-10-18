"""Health check com verificação real do PostgreSQL."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_engine

router = APIRouter(tags=["health"])


def get_health_engine() -> Engine:
    return get_engine()


@router.get("/health")
def health(engine: Annotated[Engine, Depends(get_health_engine)]) -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})
