# Domínio financeiro do Sentavos

Curto de propósito: o que é verdade onde, o que nunca pode quebrar e por onde
o dinheiro passa. O código de cada regra mora em `app/dominio/` (ver o
`__init__.py`); as rotas validam, chamam e serializam; o front só formata.

## Fontes de verdade

| Pergunta | Fonte | Derivado (nunca gravado) |
|---|---|---|
| Quanto gastei / recebi | `transactions` (competência) | gasto total, custo de vida, metas |
| Quanto saiu da conta | `transactions` à vista + `invoice_payments` + aportes | saldo do mês (`dominio/caixa.py`) |
| Quanto há na conta | `account_balance_snapshots` (observado) | saldo calculado = observado + movimentos depois (`dominio/contas.py`) |
| Quanto vale um investimento | `asset_snapshots` (fim de mês) | variação, rendimento (`dominio/investimentos.py`) |
| O que é aporte/resgate de qual ativo | `investment_movements` | aportado, resgatado, ajustado |
| Quanto devo no cartão | `purchases` → parcelas em `transactions` + `invoice_payments` | total/pago/status da fatura (`app/faturas.py`) |
| O que vem pela frente | `commitments` (+ baixas, dispensas) | cronograma, vencidas (`app/planejamento.py`) |
| O mês está confiável? | — | saúde do mês (`dominio/saude.py`) |
| Quem mexeu fora do fluxo comum | `audit_events` | — |

## Invariantes

1. **Gasto ≠ saída de caixa.** Compra no cartão é gasto no mês da parcela e sai
   da conta só quando a fatura é paga. Pagar fatura não é gasto.
2. **Aporte e resgate não são gasto nem receita.** Aporte sai da conta,
   resgate entra; os dois só mudam onde o patrimônio está.
3. **Transferência entre contas não muda gasto, receita nem patrimônio.**
   Uma operação só (`transfers`): origem ≠ destino, valor > 0, mesmo dono.
4. **Diferença de saldo não vira receita nem despesa.** "Atualizar saldo"
   grava um snapshot; a diferença para o calculado fica pendente até alguém
   revisar os movimentos ou aceitar o ajuste (aceite auditado).
5. **Saldo antigo não é saldo atual.** Conta: observado há mais de 31 dias =
   desatualizado (continua contando, marcado). Ativo: snapshot de mês anterior
   não entra no total do mês corrente.
6. **Natureza não muda o gasto total.** Consumo + aquisição + financeiro =
   gasto total, sempre.
7. **Dono:** toda chave para dado de outra tabela é composta `(user_id, id)`;
   recurso de outro usuário responde 404.
8. **Histórico não se apaga para corrigir.** Arquivar (conta, ativo,
   categoria); desfazer migração por evento de auditoria, idempotente.

## Conta × Ativo

- **Conta financeira** (`financial_accounts`): dinheiro líquido — corrente,
  pagamento, dinheiro, benefício (restrita), e `reconciliation` (o saldo
  agregado esperando divisão). Saldo = observado + movimentos com conta.
  É a base do planejamento.
- **Ativo** (`assets`): o que rende ou valoriza — caixinha, CDB, ações,
  cripto. Valor por snapshot de fim de mês. Entra no patrimônio, não no
  dinheiro disponível.
- Não se decide pelo nome ("Nubank" pode ser a conta ou a caixinha): ativo
  ambíguo vira item de conferência.

## Fluxos

- **Aporte:** lançamento de categoria investimento (valor > 0, sai da conta)
  + `investment_movement` CONTRIBUTION ligado a ele e ao ativo.
- **Resgate:** lançamento de investimento negativo (entra na conta) +
  REDEMPTION. Sem extrato, o ativo zera com nota de conciliação e o mês fica
  "precisa revisar" até o valor aparecer.
- **Ajuste:** ADJUSTMENT, sem lançamento (não é caixa).
- **Rendimento** = (final − inicial) − aportes − ajustes + resgates. Só
  "apurado" quando os dois saldos existem e todo movimento do mês está ligado.
- **Cartão:** compra → N parcelas (uma por fatura) → pagamento de fatura com
  conta de origem.
- **Compromisso:** financiamento, parcelado direto, recorrência (inclusive
  salário previsto). A baixa é o lançamento que paga a ocorrência; previsto
  nunca vira realizado sozinho.
- **Reserva (provisão):** tira do disponível do planejamento sem o dinheiro
  sair da conta.
- **Cenário:** simulação sobre o planejamento; nunca toca o realizado.

## Natureza do gasto

`CONSUMPTION` (padrão), `ASSET_ACQUISITION`, `FINANCIAL`. Efetiva = a do
lançamento ?? a padrão da categoria ?? consumo; só despesa. A baixa de um
compromisso nasce com a do compromisso. Três leituras:

- **gasto total** — tudo (metas, Início, regra de sempre);
- **custo de vida** — só consumo;
- **compromissos financeiros** — só financeiro.

Ex.: Moto em out/2026 — entrada da Hunter (aquisição), parcelas do
financiamento (financeiro), equipamentos (consumo).

## Decisões (mini-ADRs)

- **Sem partidas dobradas.** Contas + snapshots + movimentos tipados
  respondem o que o app precisa; um razão contábil seria a segunda fonte.
- **Snapshot com instante (`observed_at`), lançamento com data.** O
  lançamento ganhou `occurred_at` opcional; sem ele, o lançamento do mesmo dia
  não é somado novamente, mas a ordem é ambígua e o saldo fica marcado como
  incompleto. Não é confirmação de que o movimento já estava no saldo.
- **Posição observada de investimento é independente do fluxo.** Não se soma
  aporte a um snapshot mensal que pode já incluí-lo. `position_pending` avisa
  sobre movimentos sem observação posterior, inclusive os feitos sem plano.
  No mesmo dia, `AssetSnapshot` só tem data: continua exigindo conferência.
  `has_observation=false` é ausência de saldo, nunca saldo observado zero.
- **Agregado e bancos individuais podem se sobrepor.** Meu mês não apresenta
  total/projeção confirmados nessa situação; Contas exibe a pendência. A escolha
  explícita `include_in_planning` define as contas livres do mês. Os valores e
  snapshots originais são preservados até distribuir/reconciliar o agregado.
- **Responsabilidade de uma parcela é analítica.** `Transaction.finalidade`
  pode mudar em uma parcela via `/transactions/{id}/responsabilidade`, sem
  trocar `Purchase.card_id`, fatura, valor ou conta de desembolso. Edição de
  descrição da compra preserva atribuições individuais; alterar explicitamente
  sua finalidade continua valendo para todas as parcelas.
- **Estado do mês derivado, sem tabela de pendências.** Pendência gravada
  envelhece; derivada nunca discorda dos dados.
- **Migração de dado por plano explícito** (`scripts/foundation_v3.py`):
  seco por padrão, `--apply` grava com backup e auditoria, `--undo` desfaz.
- **Produção só com `APP_ENV=production` e `ALLOW_PRODUCTION_DATABASE=true`**
  em ferramenta local (`app/ambiente.py`).
