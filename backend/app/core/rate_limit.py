"""Rate limiting em memória (slowapi).

LIMITAÇÃO documentada: o armazenamento em memória vale para UMA instância
do processo. Em um cenário multi-instância (fora do escopo do MVP), será
preciso um backend compartilhado (decisão posterior).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
