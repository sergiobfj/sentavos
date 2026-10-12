"""O rastro mínimo das mudanças financeiras fora do fluxo comum.

Quem registra: conferência (aceitar diferença de saldo, distribuir saldo
agregado), transferências, movimentos de investimento, scripts administrativos
e migração de dado. Quem NÃO registra: navegação, edição de texto, o lançamento
do dia a dia. `registrar` só adiciona à sessão — quem chama decide o commit,
então o evento cai junto com a operação se ela falhar.
"""

import logging
from typing import Any

from sqlmodel import Session

from app.models import AuditEvent

log = logging.getLogger("sentavos.auditoria")

# Nunca vai pro rastro, em nenhuma profundidade.
_PROIBIDAS = ("senha", "password", "token", "secret", "segredo", "hash", "authorization")


def _limpar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {
            k: _limpar(v) for k, v in valor.items()
            if not any(p in str(k).lower() for p in _PROIBIDAS)
        }
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def registrar(
    session: Session,
    *,
    acao: str,
    ator: str,
    user_id: int | None,
    entidade: str | None = None,
    entidade_id: int | None = None,
    detalhes: dict[str, Any] | None = None,
) -> AuditEvent:
    evento = AuditEvent(
        user_id=user_id,
        actor=ator,
        action=acao,
        entity_type=entidade,
        entity_id=entidade_id,
        details=_limpar(detalhes) if detalhes else None,
    )
    session.add(evento)
    log.info("auditoria %s por %s (%s %s)", acao, ator, entidade or "-", entidade_id or "-")
    return evento


def ator_api(email: str) -> str:
    return f"api:{email}"
