# Reconciliação direcionada de outubro de 2026

Rotina: `scripts/reconciliar_outubro_2026.py`. Preserva contratos de API, modelos,
migrations e experiência visual. A correção em `app/planejamento.py` limita os
saldos e avisos das consultas históricas ao fim do mês selecionado: observações
e movimentos de meses futuros não podem reaparecer no passado. O mês corrente
e o horizonte futuro continuam usando o saldo de agora.

O inventário financeiro, plano de alterações e relatórios do ensaio ficam em
`backups/` e `.local/`, fora do Git. Não versionar esses arquivos nem credenciais.
O relatório privado desta execução é `.local/reconciliacao-outubro-2026-relatorio.md`.

## Procedimento

1. Obter fotografia recente do titular, com transação de leitura consistente e
   `READ ONLY`. Registrar revisão do schema, instante e hash do arquivo.
2. Restaurar em banco **novo** local, mantendo IDs, sequências, quatro contas,
   transações, compras, faturas, snapshots e auditoria; não importar cópia antiga
   sobre banco de uso cotidiano. Conferir contagens e schema.
3. Construir plano com `user_id`, `period: "2026-10"`, `baseline_sha256` calculado
   por `fingerprint(session, user)` e operações específicas. Toda atualização
   precisa do ID, estado completo esperado e campos propostos; toda inserção
   tem chave idempotente explícita. Cada operação inclui motivo, evidência,
   confiança e efeito no caixa. Revisar o mapa antes de aplicar.
4. Executar sem `--apply`: somente consultas e relatório privado. Se qualquer
   linha ou o inventário tiver mudado, auditar novamente; não forçar precondições.
5. Aplicar somente na cópia. A rotina cria backup com hash antes de qualquer
   alteração e mantém antes/depois em evento de auditoria na mesma transação.
6. Repetir o mesmo plano: zero alterações, nenhum novo evento/backup ou movimento.
   Comparar fontes de Meu mês, Lançamentos, Contas, Relatórios e Investir, inclusive
   períodos passados e filtros de finalidade.

```powershell
$env:APP_ENV = 'test'
$env:DATABASE_URL = 'postgresql://postgres@127.0.0.1:54329/sentavos_reconciliacao_20261020_ensaio'
.venv/Scripts/python.exe -m scripts.reconciliar_outubro_2026 --usuario '<titular>' --plano .local/plano.json --report .local/dry-run.json
# Somente após conferir o dry-run da cópia:
.venv/Scripts/python.exe -m scripts.reconciliar_outubro_2026 --usuario '<titular>' --plano .local/plano.json --report .local/aplicado.json --apply
```

## Travas e semântica

- Produção e banco local cotidiano são recusados, inclusive com `--apply`.
  PostgreSQL local precisa do prefixo `sentavos_reconciliacao_202610` e ambiente
  `test`/`development`. SQLite é aceito para os testes isolados.
- Escrita em transação serializável no PostgreSQL, com bloqueio do titular,
  precondições de todas as operações verificadas antes das mutações e impressão
  digital do inventário. Divergência/concorrência aborta sem commit parcial.
- Só a previsão avulsa sem valor realizado ou vínculos pode ser retirada para
  representar a mesma cotação na conferência. Backup e auditoria preservam sua
  linha original. Não há exclusão de compra, parcela ou pagamento real.
- Compra com pagamento de fatura é bloqueada. Correção de data exige competências
  coerentes e o mesmo ciclo de faturas, calculado pelas funções existentes;
  parcelas mantêm IDs e valores. Mudança de ciclo exige conferência separada.
- Saldo observado posterior bloqueia a inclusão de referência antiga. Saldo
  agregado não é distribuído entre bancos nem convertido em receita.
- Abatimento não cria transação. Recebível novo é apenas previsão pontual de
  entrada; resgate sem extrato vira pendência sem valor inventado.
- Nenhuma correção ocorre por busca global de descrição/valor. FKs e vínculos
  são validados pelo titular, e o plano identifica precisamente o registro.

## Validação automatizada

`app/tests/test_reconciliacao_outubro_2026.py` usa dados sintéticos e cobre:
ciclo MP 08/13 com quatro parcelas, anotação antiga presente/removida,
abatimentos 01/02 e janeiro 03, ausência de crédito pela diferença do CDC,
restituição prevista/recebida uma vez, cotação única, academia individual,
faturas sem duplicação de consumo, fotografia posterior protegida,
resgate/rendimento não apurado, aporte previsto/editado/cancelado/confirmado,
despesas previstas fixas/variáveis, finalidades, titularidade, consistência
das fontes e repetição idempotente. Casos de estado alterado, pagamento real,
fatura paga e ciclo divergente devem falhar antes de qualquer gravação.
Uma regressão específica verifica que setembro não herda snapshots de outubro,
e que outubro não herda snapshots/movimentos de novembro nem seus avisos.

```powershell
.venv/Scripts/python.exe -m pytest app/tests/test_reconciliacao_outubro_2026.py -q
```

Nesta execução: 548 testes na suíte completa e 73 regressões direcionadas
aprovados (17 casos novos de reconciliação/histórico). TypeScript e build do
frontend aprovados. O único aviso é a depreciação preexistente do TestClient.
Na cópia PostgreSQL, a primeira aplicação teve 23 operações; repetições tiveram
zero alterações e nenhum novo backup/evento.

O ensaio desta rodada corrigiu divergências na cópia, mantendo despesas
realizadas, faturas e relatórios históricos. Isso não fecha o mês: dados de
resgate, vínculos bancários e destinação da diferença do CDC continuam exigindo
conferência. Produção foi apenas consultada; escrita, merge, push e deploy não
fazem parte desta execução.
