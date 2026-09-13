"""Um só jeito de tocar no dado de alguém.

Com três contas no mesmo banco, o filtro por dono deixou de ser detalhe: se ele
faltar em **um** dos 31 pontos de consulta da API, uma pessoa lê as finanças da
outra. Não é um bug que aparece testando na mão — só aparece quando alguém nota.

Por isso não há filtro escrito à mão espalhado pelas rotas. Há estas três
funções, que já nascem filtradas, e uma regra: rota que precisa de dado usa
elas. Escrever `select(Transaction)` cru passa a ser a exceção visível numa
revisão, em vez de o padrão que ninguém percebe faltando.

A rede de segurança de verdade está em `app/tests/test_isolamento.py`, que
percorre as rotas e prova que uma conta não alcança o dado da outra. Comentário
envelhece; teste quebra.
"""

from typing import TypeVar

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, select

from app.models import User

T = TypeVar("T", bound=SQLModel)


def consulta(modelo: type[T], dono: User):
    """`select(modelo)` já preso ao dono. Ponto de partida de toda listagem."""
    return select(modelo).where(modelo.user_id == dono.id)


def buscar(session: Session, modelo: type[T], id_: int, dono: User) -> T | None:
    """Busca por id, mas só acha se for do dono. Devolve None caso contrário.

    Substitui `session.get(Modelo, id)`, que ignora dono e devolveria a linha de
    qualquer pessoa a quem soubesse o id — e os ids são sequenciais, então
    "adivinhar" é contar de 1 em diante.
    """
    achado = session.get(modelo, id_)
    if achado is None or achado.user_id != dono.id:
        return None
    return achado


def exigir(session: Session, modelo: type[T], id_: int, dono: User, oque: str) -> T:
    """Como `buscar`, mas estoura 404 em vez de devolver None.

    404 e não 403 de propósito: 403 confirmaria que a linha existe e é de
    outra pessoa. 404 não distingue "não existe" de "não é seu", que é a única
    resposta que não entrega informação sobre a conta alheia.
    """
    achado = buscar(session, modelo, id_, dono)
    if achado is None:
        raise HTTPException(status_code=404, detail=f"{oque} não encontrado.")
    return achado
