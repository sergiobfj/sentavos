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
  - `natureza_lancamento`: {transaction_id, nature, confere: {amount_paid?, description?}}
    Natureza de um gasto (ex.: a entrada da moto = asset_acquisition).
  - `natureza_compromisso`: {commitment_id, nature, confere: {amount?, description?}}
    Natureza do compromisso e das baixas que ainda tinham a anterior (ex.: o
    financiamento = financial). `confere` protege contra id trocado: se o
    lançamento/compromisso não bater, o script para sem gravar nada.

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
    Category,
    CategoryType,
    Commitment,
    FinancialAccount,
    InvoicePayment,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    SnapshotSource,
    Transaction,
    TransactionNature,
    Transfer,
)

SCRIPT = "foundation_v3"
ATOR = f"script:{SCRIPT}"


class Plano:
    def __init__(self, session, dono, aplicar: bool):
        self.s, self.dono, self.aplicar = session, dono, aplicar
        self.feitas = 0
        # No seco o renome não é gravado; as ações seguintes do plano já usam o
        # nome novo, então o seco resolve o nome novo pro antigo.
        self.renomes: dict[str, str] = {}

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
        todos = self.s.exec(consulta(Asset, self.dono)).all()
        achados = [a for a in todos if a.name.casefold() == nome.casefold()]
        if not achados and nome.casefold() in self.renomes:
            achados = [a for a in todos if a.name.casefold() == self.renomes[nome.casefold()].casefold()]
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
        if not ja and not self.aplicar:
            self.renomes[novo.casefold()] = a["asset"]
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

    def movimento_investimento(self, a: dict) -> None:
        """Liga um lançamento de investimento ao ativo (aporte/resgate explícito)."""
        from app.dominio import investimentos
        from app.models import InvestmentMovementCreate

        t = self.s.get(Transaction, a["transaction_id"])
        if t is None or t.user_id != self.dono.id:
            sys.exit(f"Lançamento {a['transaction_id']} não é desta conta.")
        ativo = self.ativo(a["asset"])
        existente = investimentos.movimento_do_lancamento(self.s, self.dono, t.id)
        self.log(existente is not None, f"lançamento {t.id} ({t.description}, {t.amount_paid:.2f} em "
                                        f"{t.date:%d/%m}) = {a['type']} do ativo '{ativo.name}'")
        if existente or not self.aplicar:
            return
        conta = self.conta(a["account"]) if a.get("account") else None
        mov = investimentos.registrar(self.s, self.dono, InvestmentMovementCreate(
            asset_id=ativo.id, type=a["type"], amount=abs(t.amount_paid), date=t.date, transaction_id=t.id,
            account_id=conta.id if conta else None, note=a.get("note")), ATOR)
        self.registrar("movimento_investimento", {"movement_id": mov.id, "transaction_id": t.id,
                                                  "conta_definida": bool(conta)}, "investment_movement", mov.id)

    def _conferir(self, obj, rotulo: str, confere: dict | None) -> None:
        for campo, esperado in (confere or {}).items():
            valor = getattr(obj, campo, None)
            igual = abs(float(valor or 0) - float(esperado)) < 0.005 if isinstance(esperado, (int, float)) \
                else str(valor or "").casefold() == str(esperado).casefold()
            if not igual:
                sys.exit(f"{rotulo}: {campo} é {valor!r}, o plano esperava {esperado!r}. Nada foi gravado.")

    def _despesa(self, category_id: int, rotulo: str) -> None:
        cat = self.s.get(Category, category_id)
        if cat is None or CategoryType(cat.type) != CategoryType.EXPENSE:
            sys.exit(f"{rotulo}: só despesa tem natureza.")

    def natureza_lancamento(self, a: dict) -> None:
        t = self.s.get(Transaction, a["transaction_id"])
        if t is None or t.user_id != self.dono.id:
            sys.exit(f"Lançamento {a['transaction_id']} não é desta conta.")
        rotulo = f"lançamento {t.id} ({t.description}, {t.amount_paid or 0:.2f} em {t.date:%d/%m/%Y})"
        self._conferir(t, rotulo, a.get("confere"))
        self._despesa(t.category_id, rotulo)
        nova = TransactionNature(a["nature"])
        atual = TransactionNature(t.nature) if t.nature else None
        self.log(atual == nova, f"{rotulo}: natureza {nova.value}")
        if atual == nova or not self.aplicar:
            return
        t.nature = nova
        self.s.add(t)
        self.s.flush()
        self.registrar("natureza_lancamento", {"transaction_id": t.id, "de": atual.value if atual else None,
                                               "para": nova.value}, "transaction", t.id)

    def natureza_compromisso(self, a: dict) -> None:
        from app.dominio import natureza

        c = self.s.get(Commitment, a["commitment_id"])
        if c is None or c.user_id != self.dono.id:
            sys.exit(f"Compromisso {a['commitment_id']} não é desta conta.")
        rotulo = f"compromisso {c.id} ({c.description}, {c.amount:.2f})"
        self._conferir(c, rotulo, a.get("confere"))
        self._despesa(c.category_id, rotulo)
        nova = TransactionNature(a["nature"])
        atual = TransactionNature(c.nature) if c.nature else None
        baixas = self.s.exec(consulta(Transaction, self.dono).where(Transaction.commitment_id == c.id)).all()
        levar = [t for t in baixas if (TransactionNature(t.nature) if t.nature else None) == atual]
        self.log(atual == nova, f"{rotulo}: natureza {nova.value}, e {len(levar)} baixa(s) já paga(s) junto")
        if atual == nova or not self.aplicar:
            return
        c.nature = nova
        self.s.add(c)
        mudadas = natureza.levar_as_baixas(self.s, self.dono, c, atual)
        self.s.flush()
        self.registrar("natureza_compromisso", {"commitment_id": c.id, "de": atual.value if atual else None,
                                                "para": nova.value, "baixas": mudadas}, "commitment", c.id)

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
            elif acao == "movimento_investimento":
                from app.models import InvestmentMovement
                mov = self.s.get(InvestmentMovement, d["movement_id"])
                if mov and mov.user_id == self.dono.id:
                    self.s.delete(mov)
                if d.get("conta_definida"):
                    t = self.s.get(Transaction, d["transaction_id"])
                    if t and t.user_id == self.dono.id:
                        t.account_id = None
                        self.s.add(t)
            elif acao == "revisar_ativo":
                item = self.s.get(ReconciliationItem, d["item_id"])
                if item and item.user_id == self.dono.id and item.status == ReconciliationStatus.PENDENTE:
                    self.s.delete(item)
            elif acao == "natureza_lancamento":
                t = self.s.get(Transaction, d["transaction_id"])
                if t and t.user_id == self.dono.id and t.nature and TransactionNature(t.nature).value == d["para"]:
                    t.nature = TransactionNature(d["de"]) if d["de"] else None
                    self.s.add(t)
            elif acao == "natureza_compromisso":
                c = self.s.get(Commitment, d["commitment_id"])
                if c and c.user_id == self.dono.id and c.nature and TransactionNature(c.nature).value == d["para"]:
                    c.nature = TransactionNature(d["de"]) if d["de"] else None
                    self.s.add(c)
                for tid, antes in d.get("baixas", []):
                    t = self.s.get(Transaction, tid)
                    if t and t.user_id == self.dono.id and t.nature and TransactionNature(t.nature).value == d["para"]:
                        t.nature = TransactionNature(antes) if antes else None
                        self.s.add(t)
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
