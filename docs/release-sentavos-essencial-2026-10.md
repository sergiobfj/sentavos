# Release Sentavos Essencial — procedimento de publicação

Estado preparado em 19/10/2026, branch `feat/sentavos-essencial`, PR #2.
**Duas autorizações separadas são obrigatórias:** (A) merge e deploy de código;
(B) reconciliação financeira em produção. A autorização A não implica B.

## Evidência e limite do backup

O inventário de produção `production-validation-20261020T005000Z.json` contém
**991 linhas em 22 tabelas**. Uma é a linha técnica de `alembic_version`.
No ensaio local, Alembic criou essa linha ao instalar o esquema; **as outras
990 linhas foram carregadas**, e todos os valores das 21 tabelas de aplicação
foram comparados com o inventário: zero diferenças. O arquivo inclui dados
sensíveis e fica em `.local/`, fora do Git. É backup lógico de linhas e colunas;
não substitui um ponto de recuperação do Neon para o esquema inteiro.

A migration `0013_abatimento_compromisso` entrou na `main` pelo commit
`63a7d3c`, ancestral de `9ad0506` e anterior ao PR #2. O backend aplica
`alembic upgrade head` no startup. Produção reporta `0013`, coerente com
esse histórico; o PR #2 não contém migrations. A API da branch leu uma cópia
fiel do banco atual em `0013` pelas rotas de Contas, planejamento, faturas,
transações, compromissos e conferência. A única mudança de contrato no backend
do PR é recusar com 409 uma segunda criação para um item de conferência já
decidido; o frontend antigo continua compatível.

## Ponto de recuperação Neon — condição de liberação

Antes de qualquer escrita financeira, na conta Neon que hospeda `neondb`:

1. Identificar a branch de produção ligada ao endpoint do Render. Criar uma
   **branch filha da produção no estado corrente** (ou snapshot persistente
   equivalente), com nome `release-essencial-pre-dados-<timestamp>`, sem TTL
   antes de terminar a validação. Anotar ID `br-...`, horário e branch mãe.
2. Abrir a conexão da branch filha e confirmar `alembic_version=0013`, 991
   linhas, as quatro contas, `purchases.id=49` e `transactions.id=1168`
   (Uber R$5,80). Confirmar que ela está isolada da conexão de produção.
3. Capturar outro inventário lógico somente leitura imediatamente antes de
   aplicar dados. O estado da branch de recuperação e do novo inventário deve
   ser o mesmo; se houver mudança, criar novo ponto e repetir o pré-voo.

O ID verificado da branch de recuperação é exigido pela rotina de aplicação.
Sem esse ID e a verificação acima, **a etapa B não começa**. Neon permite
criar uma branch isolada do estado da produção e recuperar linhas dela sem
rebobinar as escritas posteriores ([branching](https://neon.com/docs/get-started-with-neon/workflow-primer),
[recuperação seletiva](https://neon.com/blog/recover-production-database)).

## A — deploy do código, sem reconciliação financeira

1. Antes do merge autorizado, em **Vercel → projeto → Settings → Environments
   → Production → Branch Tracking**, desligar temporariamente **Auto-assign
   Custom Production Domains**. Isto deixa o deploy da `main` preparado, sem
   trocar o domínio público; não pausa o site nem altera proteção da `main`.
   Registrar o valor anterior do ajuste.
2. Fazer o merge do PR #2 somente após autorização A e checks verdes. Render
   publica a nova API primeiro. Confirmar o SHA implantado, health check e
   consultas autenticadas somente leitura de `/accounts/summary`,
   `/planning/month`, `/commitments/7`, `/reconciliation` e faturas.
3. Confirmar que o build Vercel do mesmo SHA está **Staged**. Promovê-lo ao
   domínio público após a API saudável; conferir Contas e pagamentos.
4. Restaurar **Auto-assign Custom Production Domains** ao valor anterior.
   Registrar SHAs/URLs dos dois deploys. Se Render falhar, manter o front
   antigo e usar o rollback do último deploy íntegro do Render. Se o front
   falhar, usar o rollback instantâneo Vercel.

Referências operacionais: [deploys e rollback Render](https://render.com/docs/deploys),
[staging e promoção Vercel](https://vercel.com/docs/deployments/promoting-a-deployment).

O backend do PR #2 não altera dados no startup: o Alembic encontra `0013` já
aplicada. O procedimento A não executa a rotina financeira abaixo.

## B — reconciliação financeira direcionada

Executar **somente após autorização B**, com o ponto Neon verificado e novo
backup lógico. `scripts/reconciliar_essencial_20261019.py` é somente leitura
por padrão. A opção `--apply` exige backup e hash exato, ID `br-...` da branch
de recuperação, ambiente de produção explícito e trava da conexão remota.
A aplicação usa uma transação serializável e falha se qualquer linha ou coluna
mudou desde o backup.

O pré-voo recusa novos pagamentos em dinheiro, pagamentos de fatura,
transferências, movimentos de investimento ou saldos observados depois da
referência de 19/10. `amount_paid` em parcelas futuras de cartão não é baixa
da fatura. Se houver movimento novo, recalcular o saldo com o titular e refazer
backup, branch e plano; não forçar R$668,96.

Se as condições persistirem, aplicar somente:

- novo snapshot de **R$668,96** na conta agregada já existente (`id=4`), sem
  apagar o histórico de R$684,39 e sem distribuir R$418,96/R$250 por banco;
- vencimento previsto de R$720 em `commitments.id=15` e
  `transactions.id=936` para 20/10, mantendo a entrada de R$700 (`id=937`);
- categoria de reembolso, se ausente, e uma única transação **prevista**, não
  recebida, de R$550 até 28/10, com ID gerado pelo banco;
- Hunter `id=7` com dia contratual 12 e total informativo R$16.469,24;
  ocorrências 01 e 02 abatidas em 15/10, sem transação financeira; 03/48 em
  12/01/2027;
- itens de conferência `4` e `5` marcados para confirmar os recebimentos
  previstos. Um evento de auditoria registra backup, branch e alterações.

O script não importa nem substitui a cópia antiga. Preserva `purchases.id=49`,
`transactions.id=1168` (Uber R$5,80), as quatro contas, seus investimentos e
os demais registros posteriores a 12/10. O ensaio na cópia atual passou duas
vezes; na repetição, `applied=[]`. A API retornou R$668,96, R$1.970 previstos,
Hunter 03/48 em janeiro e fatura Sergio de novembro R$71,70, incluindo Uber.

**Emplacamento:** a anotação de produção é R$908; a evidência local menciona
R$904 em 4×R$226. O script não cria compra, parcelas, fatura nem pagamento e
não altera essa pendência. Cartão, valor final e primeiro vencimento exigem
conferência específica.

## Recuperação se algo falhar

O script financeiro confirma todas as alterações em **uma transação**. Erro
antes do commit desfaz a transação inteira. Depois do commit, registrar um
novo backup e comparar produção ao ponto Neon. Para uma divergência limitada,
restaurar **somente as linhas afetadas**, com pré-condições que impeçam apagar
movimentos posteriores. A branch de recuperação fornece os valores anteriores;
o evento de auditoria identifica os IDs alterados.

Para incidente amplo, criar primeiro uma cópia do estado pós-incidente e
confrontar todos os registros novos. Usar o recurso de restore do Neon somente
após decidir como preservar essas escritas: restaurar a branch inteira sobre
produção substitui o estado posterior ao ponto. Nunca restaurar a cópia de
12/10 por cima da produção. Depois de qualquer recuperação, conferir saldo,
entradas, faturas, Uber, quatro contas e Hunter pelas rotas da API.

## Checklist de autorização

- [ ] Branch/snapshot Neon criado, ID e restauração de leitura verificados.
- [ ] **Autorização A:** merge do PR #2 e deploy controlado Render → Vercel.
- [ ] Verificação do código publicado, sem escrita financeira.
- [ ] Novo backup, comparação e pré-voo de movimentos posteriores ao saldo.
- [ ] **Autorização B:** executar `--apply` da reconciliação financeira.
- [ ] Verificação pós-aplicação e guarda do ponto de recuperação.
