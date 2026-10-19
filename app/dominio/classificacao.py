"""Organização de despesas; nunca altera gasto, caixa ou natureza analítica."""
from app.models import CategoryType, ExpenseClass


def gravavel(tipo, valor):
    return valor if tipo == CategoryType.EXPENSE else None


def efetiva(lancamento, compromisso=None):
    if lancamento.expense_class is not None:
        return lancamento.expense_class
    if compromisso is not None:
        return compromisso.expense_class or ExpenseClass.FIXED
    return None


def do_compromisso(compromisso, tipo):
    return (compromisso.expense_class or ExpenseClass.FIXED) if tipo == CategoryType.EXPENSE else None
