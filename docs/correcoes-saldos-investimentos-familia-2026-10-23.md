# Correções de saldo, investimentos, Família e favicon — 23/10/2026

Código corrigido; produção não acessada nem alterada. Não houve push, merge ou
deploy. Sem `.env`, configuração bancária ou backup real disponível nesta
máquina, não foi possível localizar os IDs reais nem comprovar os recebimentos,
o aporte ou o pagamento do dentista. O acesso foi solicitado durante a execução.
O ensaio descrito aqui usa exclusivamente dados sintéticos em PostgreSQL local.

## Pré-voo e fontes

`origin/main` e `main` estavam em `b4078be`, conferidos após `git fetch origin`.
Branch: `fix/saldos-investimentos-familia-favicon`. A alteração anterior em
`app/models.py` (quatro campos de recorrência) e o arquivo de instruções foram
preservados fora dos commits. A verificação também usou um worktree sem essa
alteração preexistente, pois ela ainda não tem migration correspondente.
Schema aplicado nos bancos novos: `0014_investment_plans`; nenhuma migration nova.

| Informação | Fonte canônica existente |
|---|---|
| Caixa observado/calculável | `financial_accounts`, `account_balance_snapshots`; `dominio/contas.py` |
| Receita e consumo realizados | `transactions.amount_paid`; categorias e finalidade |
| Crédito e desembolso | `purchases` → parcelas em `transactions`; somente `invoice_payments` paga a fatura |
| Transferências próprias | `transfers`; não pagam automaticamente emissor/familiar |
| Posição de ativo | `assets`, `asset_snapshots`; `dominio/patrimonio.py` |
| Aporte/resgate realizado | `investment_movements` vinculado à transação de investimento |
| Intenção de investir | `investment_plans`; confirmar reutiliza o plano, com movimento único |
| Projeção/conferência | `commitments`, `provisions`, `reconciliation_items`; `planejamento.py` |
| Telas/cache | `/months/summary`, `/transactions`, `/accounts/summary`, `/investments/summary`; `queries.ts` |

## Causas e correções

- **Saldo:** a UI dizia “Tenho agora” mesmo com movimentos sem conta e projeção
  inviável. A data vem do snapshot usado, não do total de entradas. Agora informa
  “Saldo observado em…” ou “Calculado desde…”, com atualização pendente quando
  incompleto/antigo. Movimentos sem hora no mesmo dia não são somados outra vez,
  mas exigem conferência. Registros futuros não contaminam os avisos de hoje.
  Agregado e bancos possivelmente sobrepostos suspendem o total de Meu mês e a
  projeção; desmarcar explicitamente o agregado do planejamento é respeitado.
  A origem específica do snapshot de R$684,39 de 11/10 depende da base real.
- **Investir:** a posição existente depende de snapshot mensal independente do
  aporte. Não foi criado outro motor de posição. Agora todo movimento realizado
  sem observação posterior sinaliza `position_pending`, mesmo fora de planos.
  Sem snapshot aparece “Sem saldo observado” e traço; zero observado continua
  zero. A tela distingue saldo observado de “Aportado no mês” e oferece atualizar
  em Patrimônio. Patrimônio informa total parcial e não apresenta essa lacuna
  como queda patrimonial. A saúde do mês também mantém a pendência. Snapshot
  posterior não soma o aporte novamente; mesmo dia sem horário permanece
  ambíguo. Isso não comprova posição atual de R$550 nem inventa rendimento.
- **Cache:** criar/editar/excluir ativos ou snapshots invalidava somente ativos
  e planejamento. Agora invalida também Investir, Meu mês, contas e saúde, pela
  função de invalidação financeira existente. Aportes, resgates, transações,
  transferências e pagamentos já usavam essa função; seus fluxos foram mantidos.
- **Família:** editar uma parcela abria a compra inteira, sem atribuição isolada.
  Novo fluxo usa somente `Transaction.finalidade`, com auditoria idempotente.
  A parcela permanece no cartão e na fatura originais; as demais não mudam.
  Editar descrição da compra não apaga a responsabilidade individual. Pagamento
  parcial e transferência continuam operações distintas, nas rotas existentes.
- **Script:** a CLI confirmava a conexão externa sem enviar o último evento de
  auditoria pendente da sessão. O evento agora é enviado na mesma transação.
  A rotina existente ganhou `--dry-run` explícito e atribuição individual por ID,
  com estado anterior completo, titular, fingerprint e restrição a cópia local.
- **Ícones:** o HTML usava `/logo.png` amarelo. Não havia SVG nem service worker
  registrado no projeto. Os PNGs originais dos ícones foram recoloridos sem
  redesenho: branco sobre `#101319`. Novos nomes `*-white-v1` evitam reutilização
  de cache; favicon PNG/ICO, apple-touch-icon e manifest any/maskable atualizados.
  Logo interna e arquivos originais preservados. Nenhum cache offline foi apagado.

## Registros reais e evidências ainda necessárias

| Registro solicitado | ID real / classificação | Conduta |
|---|---|---|
| R$684,39 de 11/10 e R$668,96 de 19/10 | Indisponível; histórico informado | Nenhum novo saldo gravado |
| Nubank R$1.214,71 | Indisponível; instante não confirmado | Exigir data/ordem em relação ao aporte; já inclui Santander |
| Santander R$550 previsto / R$551 recebido / R$551,50 citado | Indisponível; divergência não confirmada | Não escolher valor nem dar baixa sem identificar vínculos |
| R$944,34 + R$720 + R$551 = R$2.215,34 | IDs indisponíveis | Total de entradas; nunca convertido em saldo |
| Aportes MP R$800 e Nubank R$550 | IDs/vínculos indisponíveis | Fluxo R$1.350 apenas se ambos realizados e únicos |
| Resgate MP/Hunter; Argentina R$500; entrada R$700 | Informação não confirmada | Nenhum resgate, aporte ou recebimento fabricado |
| Michele 2/5 R$112,20 | Compra/parcela/fatura/pagamento indisponíveis | Precisa origem, data, forma e comprovante; nenhum pagamento real criado |
| Transporte R$60,85; Jet R$22,17; almoço R$40 | Compras/fatura/configuração reais indisponíveis | R$123,02 é referência; não foram inseridas na base real |

Não há duplicata real comprovada. Não se inferem banco, finalidade ou fatura por
descrição. Contas não têm dimensão Pessoal/Família/Empresa própria: a seleção de
dinheiro livre usa `include_in_planning` e `restricted`; a finalidade analítica
dos gastos usa os campos já existentes. A transferência para pessoa externa
não deve virar uma conta própria fictícia ou pagamento direto de fatura.

## Ensaio isolado e limites

PostgreSQL 16.2 em `127.0.0.1:54329`, dados somente sintéticos. Backup recente da
fixture em transação `REPEATABLE READ, READ ONLY`, hash SHA-256 e restauração
em banco novo com IDs mantidos. Plano seco: uma atribuição; aplicação: uma
alteração e um evento; repetição: zero mudanças, sem novo backup/evento.
Caixa, patrimônio observado, montantes e saldo de faturas não mudam ao atribuir
responsabilidade. Planos e relatórios privados ficam em
`.local/verify-saldos/.local/saldos-*`; backups em
`.local/verify-saldos/backups/`. Não são uma cópia da produção.

IDs do ensaio validado no banco `sentavos_reconciliacao_20261023_copia_5b0372a1`
(titular sintético `user_id=3`; estes IDs **não identificam dados reais**):

| Entidade/ID sintético | Antes → depois do script | Efeito |
|---|---|---|
| `transactions/24`, compra `8`, fatura `13` | Família → Pessoal, somente parcela 2/5 R$112,20 | Atribuição analítica; compra/fatura preservadas |
| `account_balance_snapshots/4,5`, conta `3` | R$684,39 / R$1.214,71 → iguais | Nenhum snapshot de ajuste |
| `investment_movements/4,5`, ativos `6,5` | Aportes R$800 / R$550 → iguais | Fluxo mensal R$1.350; nenhuma duplicação |
| `asset_snapshots/3,4` | MP R$0 / Nubank R$550 → iguais | Posição observada da fixture, não confirmação bancária real |
| `invoice_payments/2`, fatura `13` | R$112,20 → igual; restante R$200 | Não quita a fatura inteira |
| `purchases/10,11,12` | R$60,85 / R$22,17 / R$40 → iguais | R$123,02 no cartão pessoal; caixa inalterado pelo script |

O saldo calculado de R$552,51 dessa fixture também permaneceu igual. Na montagem
dos E2E, a conta foi atualizada pela UI, o aporte confirmado uma vez, a posição
informada pela UI e um pagamento parcial explícito registrado. São operações de
teste, separadas da única atribuição aplicada pelo script na segunda cópia.

Para a base real, obter backup atual somente leitura, restaurar em cópia nova
e montar plano com IDs/estado/evidências. A ferramenta recusa remoto e banco
cotidiano, mesmo com `--apply`. Sem os dados, nenhuma correção financeira real
foi ensaiada ou aplicada; a tabela acima permanece pendente.

## Verificação

- Backend: suíte completa de 564 testes; 33 regressões de reconciliação/saldo
  novamente após o ajuste final da auditoria, sem remover testes existentes.
- PostgreSQL: migrations existentes até 0014, restauração, script real via CLI,
  backup, auditoria, precondições e repetição idempotente.
- Frontend: TypeScript e build de produção; sete E2E em Edge/Chromium com APIs
  reais e PostgreSQL local, incluindo atualização de conta e posição pela UI,
  aporte, Família, pagamento parcial, crédito e assets do manifest em claro/escuro.
- Ícones inspecionados visualmente; arquivos servidos no build. Instalação real
  em Android/iOS não foi testada. Sistemas podem manter o ícone instalado até
  atualização ou reinstalação do atalho; não apagar dados do aplicativo para isso.
- Aviso preexistente: depreciação de `httpx` no TestClient.

`frontend/tests/saldos/prepare.py` cria usuário de teste novo, sem alterar outro
usuário, somente em banco PostgreSQL local com prefixo sintético autorizado.
Configuração: `APP_ENV=test`, `DATABASE_URL` do banco isolado, API `8014`,
`CORS_ORIGINS=http://127.0.0.1:5184`, `VITE_API_URL=http://127.0.0.1:8014` no build;
preview na porta 5184 e `npx playwright test --config playwright.saldos.config.ts`.
As credenciais geradas permanecem no arquivo ignorado `.local/saldos-users.json`.
