"""Rotas de relatório: a série de meses e a distribuição por categoria.

Router próprio com `Depends(require_user)`, como o do cartão — rota nova aqui
nasce fechada. Só leem, então a conta demo usa todas.

Existem pra a tela de Início não montar número a partir de lançamento cru:
reagrupar no navegador duplicaria a regra de gasto × caixa, que já custou uma
contagem dupla. O servidor agrega; a tela desenha.
"""

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth import require_user
from app.database import get_session
from app.models import Finalidade, User
from app.relatorios import distribuicao, meses_entre, serie_mensal

router_relatorios = APIRouter(dependencies=[Depends(require_user)])

# Três anos. É teto contra pedido absurdo, não regra de produto: a tela pede 6
# ou 12 meses.
MAX_MESES = 36

MES = re.compile(r"^(\d{4})-(\d{2})$")

# "todos" é o padrão e o único que inclui gasto sem finalidade.
FiltroFinalidade = Literal["todos", "pessoal", "familia", "empresa"]


def _mes(texto: str, campo: str) -> tuple[int, int]:
    achado = MES.match(texto or "")
    if not achado or not 1 <= int(achado.group(2)) <= 12 or not 1900 <= int(achado.group(1)) <= 2999:
        raise HTTPException(status_code=400, detail=f"'{campo}' deve ser AAAA-MM.")
    return int(achado.group(1)), int(achado.group(2))


def _finalidade(filtro: FiltroFinalidade) -> Finalidade | None:
    return None if filtro == "todos" else Finalidade(filtro)


@router_relatorios.get("/reports/monthly")
def relatorio_mensal(
    de: str = Query(alias="from", description="Primeiro mês, AAAA-MM"),
    ate: str = Query(alias="to", description="Último mês, AAAA-MM (inclusive)"),
    finalidade: FiltroFinalidade = Query(default="todos"),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Um ponto por mês entre `from` e `to`, meses vazios inclusive.

    `finalidade` estreita só o gasto. Entrada, investimento, faturas pagas e
    saldo do mês são sempre da conta inteira.
    """
    inicio, fim = _mes(de, "from"), _mes(ate, "to")
    if fim < inicio:
        raise HTTPException(status_code=400, detail="'to' vem antes de 'from'.")
    if len(meses_entre(inicio, fim)) > MAX_MESES:
        raise HTTPException(status_code=400, detail=f"No máximo {MAX_MESES} meses por vez.")

    return {
        "finalidade": finalidade,
        "months": serie_mensal(session, dono, inicio, fim, _finalidade(finalidade)),
    }


@router_relatorios.get("/reports/categories")
def relatorio_categorias(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    finalidade: FiltroFinalidade = Query(default="todos"),
    top: int = Query(default=5, ge=1, le=12),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Gasto do mês por categoria, as `top` maiores e o resto agrupado."""
    return distribuicao(session, dono, year, month, _finalidade(finalidade), top)
