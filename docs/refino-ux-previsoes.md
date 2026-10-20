# Refino de UX e previsões

Decisões de implementação (20/10/2026):

- `InvestmentPlan` é a representação canônica de novos aportes/resgates previstos. Não cria lançamento, movimento ou snapshot. Planos antigos de categoria investimento continuam sendo lidos pelo planejamento, sem migração de dados.
- A confirmação bloqueia a linha do plano no Postgres e reutiliza o serviço de movimentos. Uma realização por plano; retry retorna a mesma realização. Conta e categoria são exigidas ao confirmar, não ao planejar.
- Posições de investimento continuam sendo saldos observados mensais, como no domínio existente. Confirmar registra o fluxo; o saldo do ativo deve ser informado pelo extrato. Não inferimos rendimento nem saldo bancário do ativo.
- Após confirmar, `balance_pending` impede apurar rendimento sobre um saldo anterior ao movimento. Informar novamente o saldo do ativo limpa essa pendência. Nenhum snapshot é criado ou alterado ao planejar ou confirmar.
- O planejamento continua reunindo faturas, recorrências e despesas avulsas. Previsão com valor e data informados é obrigação confirmada, sem ser pagamento. Estimativa incerta permanece separada.
- O resumo mensal do servidor é compartilhado por Meu mês e Contas. Parte do saldo calculado das contas, que já aplica movimentos posteriores ao snapshot. Base incompleta impede promessa de sobra confiável.
- Compras de cartão são gasto reconhecido; pagamento de fatura é saída de caixa. O rótulo do resumo não pode chamar compras de pagas.
- Nenhum dado de produção será alterado. A auditoria do emplacamento usa cópia local; eventual correção de produção exige procedimento de release próprio.

## Interface

Meu mês reúne saldo conhecido com data e previsão em uma superfície compacta;
abaixo, três indicadores de fluxo e a linha A investir. O detalhamento dos
quatro grupos abre ao toque. Compras no cartão aparecem como gasto reconhecido,
sem a legenda Pago. Aportes realizados nunca se confundem com posição dos ativos.

O formulário passou a ter valor dominante, quatro opções compactas de tipo,
switch visível, conta/categoria em duas colunas e detalhes recolhidos. A data
prevista aparece ao ligar o switch. Fechamento protege alterações, foco fica
preso na folha e a altura acompanha `visualViewport` quando o teclado abre.

Contas usa os mesmos totais e obrigações do servidor; confirmar uma despesa
avulsa edita o registro existente. Investir mantém sua estrutura e acrescenta
os próximos planos, com edição, cancelamento e confirmação explícita. Relatórios
mantém seus cálculos e recebe apenas os tokens visuais compartilhados.

## Emplacamento

A cópia disponível (`production-validation-20261020T005000Z.json`) contém uma
anotação de R$908 sem vencimento. Nela e no banco local de revisão consultado,
não existe cartão Mercado Pago ou compra de documentação para corrigir com
segurança. Esses inventários podem estar anteriores aos movimentos recentes.
Não alteramos dados de produção nem transformamos essa anotação em pagamento.

O erro de interface foi corrigido: gasto no cartão não recebe o rótulo Pago,
e faturas não são atribuídas automaticamente às despesas fixas. O cenário
13/10/2026, R$904 em 4×226, cartão com fechamento 8 e vencimento 13 foi testado:
primeira fatura em 13/11, sem baixa à vista, com pagamento parcial correto.

`scripts/corrigir_emplacamento.py` prepara uma correção dirigida **somente em
cópia local**, seco por padrão, com cartão/categoria existentes, backup e
auditoria ao aplicar. Recusa ciclo divergente, pagamentos e possíveis duplicatas;
preserva o ID da compra, classifica como variável e vincula a anotação antiga.
Não altera financiamento, abatimentos ou saldos. A execução sobre os dados
atuais depende de um inventário atualizado e do release autorizado.

## Migração e reprodução

`0014_investment_plans` cria uma tabela. Rollback: exportar os planos antes de
`alembic downgrade 0013_abatimento_compromisso`; movimentos já confirmados ficam
preservados. O rollback remove os planos, inclusive seus vínculos de auditoria.

Para a validação integrada, iniciar o Postgres local e executar da raiz:

```powershell
uv run python frontend/tests/refino/prepare.py
$env:APP_ENV='test'
$env:DATABASE_URL='postgresql://postgres@127.0.0.1:54329/sentavos_refino'
$env:SENTAVOS_JWT_SECRET='segredo-local-refino-ux-2026-isolado-123456789'
$env:CORS_ORIGINS='http://127.0.0.1:5184'
$env:RATE_LIMIT_POR_MINUTO='2000' # carga automatizada, só neste servidor local
uv run uvicorn app.main:app --host 127.0.0.1 --port 8014
# Outro terminal, na pasta frontend:
$env:VITE_API_URL='http://127.0.0.1:8014'
npm run dev -- --host 127.0.0.1 --port 5184
# Outro terminal, na pasta frontend:
npm run test:refino
```

A preparação cria usuários sintéticos novos e escreve credenciais apenas em
`.local/`, ignorado pelo Git. Não limpa dados anteriores. Antes de repetir a
suíte inteira, executar a preparação novamente.

Capturas de dados sintéticos: [Meu mês 360](refino-ux-previsoes/meu-mes-360.png),
[Meu mês 400](refino-ux-previsoes/meu-mes-400.png),
[formulário 360](refino-ux-previsoes/formulario-360.png),
[formulário 400](refino-ux-previsoes/formulario-400.png),
[detalhes 360](refino-ux-previsoes/formulario-detalhes-360.png),
[detalhes 400](refino-ux-previsoes/formulario-detalhes-400.png),
[Contas 360](refino-ux-previsoes/contas-360.png), [Contas 400](refino-ux-previsoes/contas-400.png),
[Investir 360](refino-ux-previsoes/investir-360.png), [Investir 400](refino-ux-previsoes/investir-400.png).

Responsividade automatizada em 320, 360, 400, 768 e 1440px, além de viewport
reduzida a 420px de altura. Isso verifica adaptação à área disponível; não
substitui observação do teclado em aparelhos físicos nem mede tempo humano.

## Validação final

- Backend: **531 testes aprovados**, incluindo previsões, isolamentos, dados antigos e correção dirigida do emplacamento.
- Modelo do frontend: **7 testes aprovados**.
- E2E: **11 testes aprovados** com API real e PostgreSQL local, incluindo confirmação concorrente, demo, logout, valores grandes e muitos registros.
- Migrações em Postgres: subida, rollback e reaplicação aprovados; fixture com **533 linhas preservadas e zero divergências**.
- TypeScript e build de produção aprovados; `git diff --check` sem erros.
- Logo original preservada. Dez capturas revisadas em 360/400px. Nenhum push, merge, deploy ou alteração financeira em produção.

Os E2E usam limite de requisições ampliado só no processo local para comportar
a carga automatizada. A suíte backend valida o limitador de produção com seus
valores normais. As suítes integradas antigas dependentes da cópia histórica
de outubro não foram usadas como evidência desta entrega.
