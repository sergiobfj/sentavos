"""Natureza do gasto: consumo, aquisição de bem, financeiro.

Três leituras do mesmo gasto — nenhuma muda o gasto total:

  - **gasto total**: toda despesa, pela regra de sempre (metas, Início);
  - **custo de vida**: só CONSUMPTION — o consumo normal do mês;
  - **compromissos financeiros**: só FINANCIAL (parcela de financiamento, juros).

ASSET_ACQUISITION (a entrada da moto) entra no gasto total e fica fora das
outras duas: não é consumo do mês, e não é dívida.

A natureza que vale é a do lançamento, senão a padrão da categoria, senão
consumo — e só existe em despesa. A baixa de um compromisso nasce com a do
compromisso; mudar a do compromisso leva junto as baixas que ainda tinham a
anterior (as escolhidas à mão ficam).
"""

import sqlalchemy as sa
from sqlmodel import Session, func

from app.escopo import consulta
from app.models import Category, CategoryType, Commitment, Transaction, TransactionNature, User

CONSUMO = TransactionNature.CONSUMPTION


def efetiva(
    tipo: CategoryType | str,
    do_lancamento: TransactionNature | str | None,
    da_categoria: TransactionNature | str | None,
) -> TransactionNature | None:
    if CategoryType(tipo) != CategoryType.EXPENSE:
        return None
    escolhida = do_lancamento or da_categoria
    return TransactionNature(escolhida) if escolhida else CONSUMO


def gravavel(tipo: CategoryType | str | None, natureza: TransactionNature | None) -> TransactionNature | None:
    """O que se grava: natureza só em despesa (o resto fica nulo)."""
    if tipo is None or CategoryType(tipo) != CategoryType.EXPENSE:
        return None
    return natureza


def expressao():
    """A natureza efetiva em SQL, como NOME do enum ('CONSUMPTION'…).

    Exige o join com Category. Vale também pra receita e investimento — quem
    soma filtra o tipo antes de olhar a natureza.
    """
    return sa.type_coerce(
        func.coalesce(
            sa.type_coerce(Transaction.nature, sa.String),
            sa.type_coerce(Category.default_nature, sa.String),
            CONSUMO.name,
        ),
        sa.String,
    )


def do_nome(nome: str | None) -> str | None:
    """'ASSET_ACQUISITION' → 'asset_acquisition' (o valor que a API fala)."""
    return TransactionNature[nome].value if nome else None


def levar_as_baixas(
    session: Session, dono: User, compromisso: Commitment, anterior: TransactionNature | None
) -> list[tuple[int, str | None]]:
    """Aplica a natureza nova do compromisso às baixas que tinham a anterior.

    Devolve [(id do lançamento, natureza antiga)] — o script de migração usa
    pra desfazer. Sem commit.
    """
    nova = compromisso.nature
    mudados = []
    for t in session.exec(consulta(Transaction, dono).where(Transaction.commitment_id == compromisso.id)).all():
        atual = TransactionNature(t.nature) if t.nature else None
        if atual == (TransactionNature(anterior) if anterior else None) and atual != nova:
            mudados.append((t.id, atual.value if atual else None))
            t.nature = nova
            session.add(t)
    return mudados
