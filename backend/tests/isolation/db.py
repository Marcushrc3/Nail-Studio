"""Tabela sintética usada exclusivamente pelo harness de isolamento.

Criada e removida por fixtures de teste — NUNCA por migrations. Não faz
parte do domínio do produto.
"""

from sqlalchemy import text

PROBE_TABLE = "isolation_probe"

PROBE_DDL = text(
    f"""
    CREATE TABLE IF NOT EXISTS {PROBE_TABLE} (
        id UUID PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """
)

DROP_DDL = text(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
