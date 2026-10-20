"""Ensaio LOCAL da correção confirmada pelo usuário; seco por padrão.

Não acessa produção. Exige cartão e categoria existentes e recusa duplicatas,
pagamentos, compromissos ou saídas à vista que demandem conciliação explícita.
"""
import datetime as dt

from fastapi import HTTPException

from scripts import _admin
from app.ambiente import banco_local
from app.cartao import ciclo_da_parcela
from app.escopo import consulta, exigir
from app.models import Card, Category, CategoryType, Commitment, ExpenseClass, Purchase, Provision, Transaction, ReconciliationItem, ReconciliationStatus
from app.rotas_cartao import _gerar_parcelas, _faturas_da_compra, _limpar_faturas_vazias, _parcelas_pagas

DATA = dt.date(2026, 10, 13)


def candidatos(session, dono, model, campo="description"):
    return [r for r in session.exec(consulta(model, dono)).all()
            if any(s in getattr(r, campo).casefold() for s in ("emplac", "documenta"))]


def preparar(session, dono, card_id, category_id):
    card = exigir(session, Card, card_id, dono, "Cartão")
    cat = exigir(session, Category, category_id, dono, "Categoria")
    if card.name.casefold().strip() != "mercado pago" or card.archived:
        raise ValueError("Selecione o cartão Mercado Pago existente e ativo; nenhum cartão será inventado.")
    if ciclo_da_parcela(DATA, card.closing_day, card.due_day) != (dt.date(2026,11,8),dt.date(2026,11,13)):
        raise ValueError("O ciclo cadastrado diverge de fechamento 08/11 e vencimento 13/11. Conferir antes de corrigir.")
    if cat.type != CategoryType.EXPENSE or cat.archived:
        raise ValueError("A categoria deve ser de despesa.")
    compras = candidatos(session, dono, Purchase)
    if len(compras)>1:
        raise ValueError("Mais de uma compra candidata: concilie as duplicatas antes de continuar.")
    if candidatos(session,dono,Commitment) or candidatos(session,dono,Provision):
        raise ValueError("Existe compromisso/reserva de documentação: concilie o vínculo antes de continuar.")
    compra = compras[0] if compras else None
    avulsos = [t for t in candidatos(session,dono,Transaction) if compra is None or t.purchase_id != compra.id]
    if avulsos:
        raise ValueError("Há lançamentos candidatos fora da compra. Revise-os explicitamente para não duplicar gasto ou caixa.")
    if compra and _parcelas_pagas(session,dono,compra):
        raise ValueError("A compra já tem fatura com pagamento. Preservar o histórico e conciliar antes de alterar.")
    if len(candidatos(session,dono,ReconciliationItem))>1:
        raise ValueError("Há várias anotações de documentação: revise os vínculos antes de alterar.")
    return card,cat,compra


def aplicar(session,dono,card,cat,compra):
    """Uma compra, quatro parcelas; nenhuma transação à vista."""
    antigas = _faturas_da_compra(session,dono,compra) if compra else []
    if compra:
        for t in session.exec(consulta(Transaction,dono).where(Transaction.purchase_id==compra.id)).all():
            session.delete(t)
        session.flush()
    else:
        compra=Purchase(user_id=dono.id,card_id=card.id,category_id=cat.id,
                        description="Emplacamento Hunter",total_amount=904,installments=4,purchase_date=DATA)
    compra.card_id,compra.category_id=card.id,cat.id
    compra.total_amount,compra.installments,compra.purchase_date=904,4,DATA
    compra.expense_class=ExpenseClass.VARIABLE
    session.add(compra)
    session.flush()
    _gerar_parcelas(session,dono,compra,card)
    session.flush()
    _limpar_faturas_vazias(session,dono,antigas)
    primeira=session.exec(consulta(Transaction,dono).where(Transaction.purchase_id==compra.id,
                          Transaction.installment_no==1)).one()
    for item in candidatos(session,dono,ReconciliationItem):
        if item.commitment_id or item.provision_id:
            raise ValueError("A anotação já aponta para outra obrigação; concilie o vínculo primeiro.")
        item.transaction_id,item.status=primeira.id,ReconciliationStatus.RESOLVIDO
        item.note=((item.note or "")+f" | Emplacamento confirmado: R$904 em 4×226; anotação anterior: {item.amount}.")[:1000]
        item.amount=904
        session.add(item)
    return compra


def main():
    ap=_admin.argumentos(__doc__)
    ap.add_argument("--card-id",type=int,required=True)
    ap.add_argument("--category-id",type=int,required=True)
    args=ap.parse_args()
    if not banco_local(_admin.DATABASE_URL):
        raise SystemExit("Este ensaio só aceita banco LOCAL. Produção exige um release separado.")
    session,dono=_admin.abrir(args.usuario)
    with session:
        _admin.cabecalho("corrigir_emplacamento",dono,args.apply)
        try:
            card,cat,compra=preparar(session,dono,args.card_id,args.category_id)
        except (ValueError,HTTPException) as e:
            raise SystemExit(str(e)) from e
        print({"compra_existente":compra.id if compra else None,"cartao":card.name,
               "data":"2026-10-13","total":904,"parcelas":"4 × 226","primeiro_vencimento":"2026-11-13",
               "classe":"variable","saida_a_vista":0})
        if not args.apply:
            return
        _admin.backup(session,dono,"antes-emplacamento")
        compra=aplicar(session,dono,card,cat,compra)
        _admin.auditar(session,dono,"corrigir_emplacamento","compra.emplacamento_corrigido",{"purchase_id":compra.id})
        session.commit()
        print("Compra corrigida na cópia local.")


if __name__=="__main__":
    main()
