"""Migração assistida da Foundation V3, por conta, a partir de um plano explícito.

    uv run python -m scripts.foundation_v3 --usuario voce@exemplo.com --plano plano.json          # seco
    uv run python -m scripts.foundation_v3 --usuario voce@exemplo.com --plano plano.json --apply  # grava
    uv run python -m scripts.foundation_v3 --usuario voce@exemplo.com --undo --apply              # desfaz

Nada é decidido por nome de ativo ou de banco: o plano diz o que fazer, uma
ação por vez, e cada ação é idempotente (rodar de novo não duplica). O plano
fica fora do git quando tem dado pessoal (ex.: `.local/plano-v3.json`).

Ações:
  - `criar_conta`: {name, type, institution?, include_in_planning?, restricted?}
    Conta nova, SEM saldo — saldo não se inventa.
  - `agregado_para_conta`: {asset, account_name?, observed_at}
    O ativo-quebra-galho "Saldo agregado" vira conta RECONCILIATION com o mesmo
    valor observado; o ativo sai a partir do mês dele (arquivado, histórico intacto).
  - `renomear_ativo`: {asset, name}
    Só o nome (ex.: a caixinha que se chamava como a conta).
  - `revisar_ativo`: {asset, pergunta?}
    Ativo ambíguo ("Nubank", "Conta": conta ou investimento?) vira item de
    conferência do mês. Não se decide sozinho.
  - `movimento_investimento`: {transaction_id, asset, type, account?}
    Liga um lançamento de investimento ao ativo (aporte/resgate explícito).
  - `natureza_lancamento`: {transaction_id, nature}
  - `natureza_compromisso`: {commitment_id, nature}

Cada ação aplicada vira um `audit_event` com o que foi criado/mudado, e é por
eles que `--undo` desfaz — na ordem inversa, pulando o que já foi desfeito.
"""

import datetime as dt
import json
import sys

from sqlmodel import select

from scripts._admin import abrir, argumentos, backup, cabecalho

from app import planejamento  # noqa: E402
from app.dominio.auditoria import registrar  # noqa: E402
from app.dominio.contas import utc  # noqa: E402
from app.escopo import consulta  # noqa: E402
from app.models import (  # noqa: E402
    AccountBalanceSnapshot,
    AccountType,
    Asset,
    AssetSnapshot,
    AuditEvent,
    FinancialAccount,
    InvoicePayment,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    SnapshotSource,
    Transaction,
    Transfer,
)

SCRIPT = "foundation_v3"
ATOR = f"script:{SCRIPT}"


class Plano:
    def __init__(self, session, dono, aplicar: bool):
        self.s, self.dono, self.aplicar = session, dono, aplicar
        self.feitas = 0

    def log(self, feito: bool, texto: str) -> None:
        print(("  já feito  " if feito else ("  APLICANDO " if self.aplicar else "  APLICAR   ")) + texto)

    def registrar(self, acao: str, detalhes: dict, entidade: str | None = None, entidade_id: int | None = None) -> None:
        registrar(self.s, acao=f"{SCRIPT}.{acao}", ator=ATOR, user_id=self.dono.id,
                  entidade=entidade, entidade_id=entidade_id, detalhes=detalhes)
        self.feitas += 1

    # ---------- helpers ----------
    def conta(self, nome: str) -> FinancialAccount | None:
        for c in self.s.exec(consulta(FinancialAccount, self.dono)).all():
            if c.name.casefold() == nome.casefold() and not c.archived:
                return c
        return None

    def ativo(self, nome: str) -> Asset:
        achados = [a for a in self.s.exec(consulta(Asset, self.dono)).all() if a.name.casefold() == nome.casefold()]
        if len(achados) != 1:
            sys.exit(f"Ativo '{nome}': {len(achados)} encontrados — o plano precisa apontar um só.")
        return achados[0]

    # ---------- ações ----------
    def criar_conta(self, a: dict) -> None:
        existente = self.conta(a["name"])
        self.log(existente is not None, f"conta '{a['name']}' ({a['type']}), sem saldo")
        if existente or not self.aplicar:
            return
        tipo = AccountType(a["type"])
        restrita = a.get("restricted", tipo == AccountType.BENEFIT)
        c = FinancialAccount(user_id=self.dono.id, name=a["name"], type=tipo, institution=a.get("institution"),
                             restricted=restrita, include_in_planning=a.get("include_in_planning", not restrita))
        self.s.add(c)
        self.s.flush()
        self.registrar("criar_conta", {"account_id": c.id, "name": c.name}, "financial_account", c.id)

    def agregado_para_conta(self, a: dict) -> None:
        ativo = self.ativo(a["asset"])
        snaps = sorted(self.s.exec(consulta(AssetSnapshot, self.dono).where(AssetSnapshot.asset_id == ativo.id)).all(),
                       key=lambda s: (s.year, s.month))
        if not snaps:
            sys.exit(f"Ativo '{ativo.name}' não tem saldo pra migrar.")
        ultimo = snaps[-1]
        nome = a.get("account_name", ativo.name)
        conta = self.conta(nome)
        feito = ativo.archived_on is not None and conta is not None
        observado = utc(dt.datetime.fromisoformat(a["observed_at"]))
        self.log(feito, f"ativo '{ativo.name}' ({ultimo.value:.2f} em {ultimo.month:02d}/{ultimo.year}) → conta "
                        f"de reconciliação '{nome}', saldo observado em {a['observed_at']}; ativo sai a partir de "
                        f"{ultimo.month:02d}/{ultimo.year}")
        if feito or not self.aplicar:
            return
        if conta is None:
            conta = FinancialAccount(user_id=self.dono.id, name=nome, type=AccountType.RECONCILIATION,
                                     include_in_planning=True, restricted=False)
            self.s.add(conta)
            self.s.flush()
        snap = AccountBalanceSnapshot(user_id=self.dono.id, account_id=conta.id, observed_at=observado,
                                      balance=ultimo.value, source=SnapshotSource.MIGRATION,
                                      note=ultimo.reconciliation_note or f"Migrado do ativo '{ativo.name}'")
        self.s.add(snap)
        ativo.archived_on = dt.date(ultimo.year, ultimo.month, 1)
        self.s.add(ativo)
        self.s.flush()
        self.registrar("agregado_para_conta", {"asset_id": ativo.id, "account_id": conta.id, "snapshot_id": snap.id,
                                                "valor": ultimo.value, "archived_on": ativo.archived_on.isoformat()},
                       "financial_account", conta.id)

    def renomear_ativo(self, a: dict) -> None:
        """Nome que distingue o ativo da conta homônima ("Mercado Pago" conta ×
        "Caixinha Mercado Pago" ativo). Só o nome; saldos e histórico ficam."""
        novo = a["name"]
        ja = [x for x in self.s.exec(consulta(Asset, self.dono)).all() if x.name == novo]
        self.log(bool(ja), f"ativo '{a['asset']}' passa a se chamar '{novo}'")
        if ja or not self.aplicar:
            return
        ativo = self.ativo(a["asset"])
        antigo = ativo.name
        ativo.name = novo
        self.s.add(ativo)
        self.s.flush()
        self.registrar("renomear_ativo", {"asset_id": ativo.id, "de": antigo, "para": novo}, "asset", ativo.id)

    def revisar_ativo(self, a: dict) -> None:
        ativo = self.ativo(a["asset"])
        hoje = planejamento.hoje()
        descricao = f"Ativo antigo “{ativo.name}”: conta ou investimento?"
        existente = self.s.exec(consulta(ReconciliationItem, self.dono).where(
            ReconciliationItem.description == descricao)).first()
        self.log(existente is not None, f"item de conferência de {hoje.month:02d}/{hoje.year}: {descricao}")
        if existente or not self.aplicar:
            return
        item = ReconciliationItem(
            user_id=self.dono.id, year=hoje.year, month=hoje.month, description=descricao,
            kind=ReconciliationKind.OUTRO, status=ReconciliationStatus.PENDENTE, source="migracao",
            question=a.get("pergunta") or "Era o dinheiro da conta (vira conta financeira) ou uma aplicação (continua ativo)?",
            suggestion="Não decidido pelo nome. O histórico de saldos fica como está nos dois casos.",
        )
        self.s.add(item)
        self.s.flush()
        self.registrar("revisar_ativo", {"asset_id": ativo.id, "item_id": item.id}, "reconciliation_item", item.id)

    def executar(self, acoes: list[dict]) -> None:
        for a in acoes:
            tipo = a.get("tipo")
            metodo = getattr(self, tipo, None) if tipo and not tipo.startswith("_") else None
            if metodo is None:
                sys.exit(f"Ação desconhecida no plano: {tipo!r}")
            metodo(a)

    # ---------- desfazer ----------
    def desfazer(self) -> None:
        eventos = list(self.s.exec(
            select(AuditEvent).where(AuditEvent.user_id == self.dono.id, AuditEvent.actor == ATOR)
            .order_by(AuditEvent.id.desc())
        ).all())
        desfeitos = {e.details.get("evento") for e in eventos if e.action == f"{SCRIPT}.desfeito" and e.details}
        for e in eventos:
            if e.action == f"{SCRIPT}.desfeito" or e.id in desfeitos:
                continue
            d = e.details or {}
            texto = f"{e.action} (evento {e.id})"
            self.log(False, "desfazer " + texto)
            if not self.aplicar:
                continue
            acao = e.action.split(".", 1)[1]
            if acao == "criar_conta":
                self._remover_ou_arquivar_conta(d["account_id"])
            elif acao == "agregado_para_conta":
                ativo = self.s.get(Asset, d["asset_id"])
                if ativo and ativo.user_id == self.dono.id:
                    ativo.archived_on = None
                    self.s.add(ativo)
                snap = self.s.get(AccountBalanceSnapshot, d["snapshot_id"])
                if snap and snap.user_id == self.dono.id:
                    self.s.delete(snap)
                    self.s.flush()
                self._remover_ou_arquivar_conta(d["account_id"])
            elif acao == "renomear_ativo":
                ativo = self.s.get(Asset, d["asset_id"])
                if ativo and ativo.user_id == self.dono.id and ativo.name == d["para"]:
                    ativo.name = d["de"]
                    self.s.add(ativo)
            elif acao == "revisar_ativo":
                item = self.s.get(ReconciliationItem, d["item_id"])
                if item and item.user_id == self.dono.id and item.status == ReconciliationStatus.PENDENTE:
                    self.s.delete(item)
            elif acao in self.desfazedores:
                self.desfazedores[acao](self, d)
            registrar(self.s, acao=f"{SCRIPT}.desfeito", ator=ATOR, user_id=self.dono.id, detalhes={"evento": e.id})
            self.feitas += 1

    def _remover_ou_arquivar_conta(self, account_id: int) -> None:
        conta = self.s.get(FinancialAccount, account_id)
        if conta is None or conta.user_id != self.dono.id:
            return
        uso = any(self.s.exec(q.limit(1)).first() is not None for q in (
            select(Transaction).where(Transaction.account_id == conta.id),
            select(InvoicePayment).where(InvoicePayment.account_id == conta.id),
            select(Transfer).where((Transfer.from_account_id == conta.id) | (Transfer.to_account_id == conta.id)),
            select(AccountBalanceSnapshot).where(AccountBalanceSnapshot.account_id == conta.id),
        ))
        if uso:
            conta.archived = True  # já tem vida própria: não se apaga histórico
            self.s.add(conta)
        else:
            self.s.delete(conta)
        self.s.flush()

    desfazedores: dict = {}


def main() -> int:
    ap = argumentos(__doc__.split("\n")[0], desfazer=True)
    ap.add_argument("--plano", help="arquivo JSON com {acoes: [...]}")
    args = ap.parse_args()
    if not args.undo and not args.plano:
        ap.error("informe --plano (ou --undo)")
    session, dono = abrir(args.usuario)
    cabecalho(SCRIPT, dono, args.apply, "| DESFAZER" if args.undo else "")
    plano = Plano(session, dono, args.apply)
    if args.apply:
        backup(session, dono, f"antes-de-{SCRIPT}{'-undo' if args.undo else ''}-{dono.email.split('@')[0]}")
    if args.undo:
        plano.desfazer()
    else:
        acoes = json.load(open(args.plano, encoding="utf-8"))["acoes"]
        plano.executar(acoes)
    if args.apply:
        session.commit()
        print(f"\n{plano.feitas} mudança(s) gravada(s).")
    else:
        session.rollback()
        print("\nSeco: nada foi gravado. Rode com --apply pra gravar.")
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
