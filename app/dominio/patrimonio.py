"""Patrimônio do mês: contas + ativos − dívidas. Uma regra, um lugar.

## Ativos (AssetSnapshot, saldo mensal)

Num mês PASSADO sem lançamento vale o último saldo lançado — é o retrato
histórico. Do mês corrente em diante, saldo de mês anterior é só o último
conhecido: aparece (com `stale` e a data), mas fica fora dos totais. Ativo
arquivado (`archived_on`) deixa de contar a partir daquele mês; antes dele, o
histórico fica como era.

## Contas (FinancialAccount)

O saldo calculado (`dominio/contas.py`) no fim do mês pedido — ou agora, do
mês corrente em diante. Conta sem saldo observado até ali não entra (é assim
que os meses anteriores às contas continuam exatamente iguais). Conta
desatualizada entra, marcada: ela tem movimentos aplicados, e a virada do mês
não some com o dinheiro.
"""

from sqlalchemy import and_, or_
from sqlmodel import Session

from app import planejamento
from app.dominio import contas as dominio_contas
from app.dominio import tempo
from app.escopo import consulta
from app.models import (
    AccountPatrimonyItem,
    Asset,
    AssetClass,
    AssetClassTotal,
    AssetSnapshot,
    AssetSummary,
    AssetSummaryItem,
    FinancialAccount,
    User,
    is_liability,
)
from app.rendimento import rendimento_do_mes


def indice(ano: int, mes: int) -> int:
    return ano * 12 + (mes - 1)


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def arquivado_em(asset: Asset, ano: int, mes: int) -> bool:
    a = asset.archived_on
    return a is not None and indice(ano, mes) >= indice(a.year, a.month)


def _instante(ano: int, mes: int):
    """Fim do mês pedido; do mês corrente em diante, agora."""
    corrente = planejamento.hoje()
    if indice(ano, mes) < indice(corrente.year, corrente.month):
        return dominio_contas.fim_do_mes(ano, mes)
    return tempo.agora()


def contas_no_mes(session: Session, dono: User, ano: int, mes: int) -> list[dominio_contas.SaldoDaConta]:
    contas = list(session.exec(consulta(FinancialAccount, dono).order_by(FinancialAccount.id)).all())
    if not contas:
        return []
    return dominio_contas.saldos(session, dono, _instante(ano, mes), contas)


def resumo(session: Session, dono: User, year: int, month: int) -> AssetSummary:
    target = indice(year, month)
    anterior = mes_anterior(year, month)
    prev_target = indice(*anterior)
    hoje = planejamento.hoje()

    snapshots = session.exec(
        consulta(AssetSnapshot, dono).where(
            or_(
                AssetSnapshot.year < year,
                and_(AssetSnapshot.year == year, AssetSnapshot.month <= month),
            )
        )
    ).all()

    # Último snapshot de cada ativo até o mês pedido, e até o mês anterior.
    latest: dict[int, AssetSnapshot] = {}
    latest_prev: dict[int, AssetSnapshot] = {}

    def keep_latest(bucket: dict[int, AssetSnapshot], snap: AssetSnapshot, idx: int):
        atual = bucket.get(snap.asset_id)
        if atual is None or indice(atual.year, atual.month) < idx:
            bucket[snap.asset_id] = snap

    for snap in snapshots:
        idx = indice(snap.year, snap.month)
        if idx <= target:
            keep_latest(latest, snap, idx)
        if idx <= prev_target:
            keep_latest(latest_prev, snap, idx)

    ativos = session.exec(consulta(Asset, dono).order_by(Asset.asset_class, Asset.name)).all()

    items: list[AssetSummaryItem] = []
    by_class = {classe.value: AssetClassTotal() for classe in AssetClass}
    total_assets = total_liabilities = 0.0
    prev_assets = prev_liabilities = 0.0
    stale_count = 0
    stale_assets = stale_liabilities = 0.0

    def vencido(s: AssetSnapshot | None, alvo: tuple[int, int]) -> bool:
        return s is not None and planejamento.saldo_desatualizado((s.year, s.month), alvo, hoje)

    for asset in ativos:
        if arquivado_em(asset, year, month):
            # Fora do mês pedido inteiro — mas o anterior pode ainda contá-lo.
            prev_snap = latest_prev.get(asset.id)
            if prev_snap and not arquivado_em(asset, *anterior) and not vencido(prev_snap, anterior):
                total = by_class[AssetClass(asset.asset_class).value]
                total.previous += prev_snap.value
                if is_liability(asset.asset_class):
                    prev_liabilities += prev_snap.value
                else:
                    prev_assets += prev_snap.value
            continue
        snap = latest.get(asset.id)
        prev_snap = latest_prev.get(asset.id)
        value = snap.value if snap else 0.0
        previous = prev_snap.value if prev_snap else 0.0
        liability = is_liability(asset.asset_class)
        stale = vencido(snap, (year, month))
        # O mês anterior segue a mesma regra: olhando novembro, um saldo de
        # setembro também não vale em outubro.
        prev_conta = not vencido(prev_snap, anterior) and not arquivado_em(asset, *anterior)

        # O rendimento esperado parte do saldo do mês ANTERIOR: é sobre ele que
        # os juros do mês incidiram. Usar o saldo atual contaria juros sobre o
        # aporte que acabou de entrar, inflando o resultado.
        esperado = None
        if asset.cdi_percent and dono.cdi_annual and previous > 0:
            esperado = rendimento_do_mes(previous, dono.cdi_annual, asset.cdi_percent, year, month)

        items.append(
            AssetSummaryItem(
                asset_id=asset.id,
                name=asset.name,
                asset_class=asset.asset_class,
                liability=liability,
                note=asset.note,
                cdi_percent=asset.cdi_percent,
                expected_yield=esperado,
                # Só conta como "deste mês" se o snapshot for do período pedido;
                # valor herdado de mês anterior não tem id pra editar aqui.
                snapshot_id=snap.id if snap and indice(snap.year, snap.month) == target else None,
                value=value,
                previous=previous,
                change=value - previous,
                as_of=f"{snap.year}-{snap.month:02d}" if snap else None,
                reconciliation_note=(
                    snap.reconciliation_note if snap and indice(snap.year, snap.month) == target else None
                ),
                stale=stale,
            )
        )

        total = by_class[AssetClass(asset.asset_class).value]
        if stale:
            stale_count += 1
            if liability:
                stale_liabilities += value
            else:
                stale_assets += value
        else:
            total.value += value
            if liability:
                total_liabilities += value
            else:
                total_assets += value
        if prev_conta:
            total.previous += previous
            if liability:
                prev_liabilities += previous
            else:
                prev_assets += previous

    # ---------- Contas ----------
    contas = contas_no_mes(session, dono, year, month)
    contas_total = sum(s.saldo for s in contas if s.saldo is not None)
    contas_antes = sum(s.saldo for s in contas_no_mes(session, dono, *anterior) if s.saldo is not None)

    return AssetSummary(
        year=year,
        month=month,
        items=items,
        by_class=by_class,
        assets=total_assets,
        liabilities=total_liabilities,
        net_worth=total_assets - total_liabilities + contas_total,
        previous_net_worth=prev_assets - prev_liabilities + contas_antes,
        stale_count=stale_count,
        stale_assets=stale_assets,
        stale_liabilities=stale_liabilities,
        accounts=[
            AccountPatrimonyItem(
                account_id=s.conta.id, name=s.conta.name, type=s.conta.type, restricted=s.conta.restricted,
                archived=s.conta.archived, balance=s.saldo, quality=s.qualidade, observed_at=s.observado_em,
            )
            for s in contas if s.saldo is not None or not s.conta.archived
        ],
        accounts_total=round(contas_total, 2),
        previous_accounts_total=round(contas_antes, 2),
    )
