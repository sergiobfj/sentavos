Reinício operacional a partir de 01/11/2026
=========================================

`0015_reinicio_operacional` acrescenta somente campos nulos; não limpa dados.
O reset fica separado em `scripts/reset_total_novembro_2026.py`, seco por padrão,
restrito a uma cópia SQLite de trabalho em `.local/`. Ele não aceita produção.
O backup e o ensaio anterior permanecem preservados.

O plano privado congela titular, IDs, estados completos e hash da base. A aplicação
revalida o plano e a base, usa uma transação, verifica todas as linhas e as FKs
antes do commit e grava auditoria. O marcador impede que uma reaplicação alcance
lançamentos novos. Uma base alterada desde a simulação exige outro plano revisado.

Lançamentos e movimentos posteriores ao corte são excluídos. Compromissos são
cancelados no corte; reservas anteriores são liberadas no corte e simulações
anteriores têm suas repetições futuras encerradas. Compras históricas preservam
seus dados e recebem um limite que impede regenerar parcelas removidas.

Faturas reiniciadas preservam sua identidade e recebem `reset_on`. Itens e
pagamentos anteriores continuam no histórico de consumo/caixa, mas não compõem
a nova cobrança. Sem novos itens ou total manual, `total` e `remaining` são nulos,
o estado é `a_preencher` e nenhum pagamento pode ser criado antes de informar valor.
`manual_total` substitui a soma dos itens: nunca cria consumo nem soma em duplicidade.

O último saldo observado antes do corte fica datado e pendente, sem reconstrução
por um fluxo incompleto. Uma nova observação manual retoma o cálculo normal.
Ativos e últimas posições anteriores são preservados, com sua referência original.

Em Contas, “Nova conta a pagar” reutiliza o formulário existente; em Faturas, basta
abrir a fatura e preencher o valor total. Os cinco destinos da navegação não mudam.

Resultados, backup utilizado, IDs, contagens, valores, cópias e capturas ficam
em `.local/reset-total-resumo.md` e nos arquivos privados ali referenciados.
Nada foi enviado ao Git remoto ou aplicado em produção. Uma aplicação futura
exigirá confirmação explícita, backup atualizado e operação direcionada;
nenhuma cópia inteira deve ser restaurada sobre produção.
