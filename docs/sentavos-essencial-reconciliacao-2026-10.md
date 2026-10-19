# Outubro de 2026 — reconciliação ensaiada em cópia local

Referência informada pelo titular: **19/10/2026**. Fonte auditada: `sentavos_essencial_review`, PostgreSQL local em `127.0.0.1:54329`, restaurado dos backups disponíveis de 12/10/2026. O backup não prova movimentos posteriores. Nenhuma consulta ou escrita deste trabalho apontou para produção.

## Antes da atualização

| Assunto | Na cópia auditada | Evidência nova / decisão |
| --- | --- | --- |
| Dinheiro livre | `AssetSnapshot` de R$684,39 observado em 11/10; nenhuma `FinancialAccount` | R$668,96 em 19/10, composto de R$418,96 + R$250 sem bancos identificados. Criar conta agregada temporária e saldo observado; manter snapshot antigo como histórico e deixar as contas financeiras substituírem a origem do planejamento. |
| Salário realizado | Transação `698`, R$944,34 em 06/10 | Preservar sem reimportar. |
| R$720 a receber | Compromisso `15` e transação prevista `936`, ambos em 15/10 | Mover ambos para 20/10; não criar segunda entrada. |
| R$700 a receber | Compromisso `16` e transação prevista `937`, 20/10 | Preservar uma única entrada. |
| Reembolso Mão na Roda | Ausente | Criar recebível pontual de R$550 até 28/10, com categoria de reembolso distinta de salário. Não marcar recebido. |
| Entrada/equipamentos/Pix | Transações `933` R$7.000, `934` R$500,61 em 10/10 e `935` R$25 em 11/10 | Preservar. A data exata da entrada continua aproximada e o Pix continua sem finalidade conhecida. |
| Hunter | Compromisso `7`, 48×R$618,08, primeira data 09/11; nenhuma dispensa ou baixa | Corrigir dia contratual para 12. Marcar ocorrências 1 e 2 como abatidas pelo credor em 15/10, sem transação; 3/48 vence 12/01/2027. |
| Documentação | Nenhuma compra de R$904 identificada | Como cartão e vencimento não foram confirmados, registrar pendência de conferência de 4×R$226; não criar fatura fictícia. |
| Faturas | Outubro: três faturas pagas. Novembro: Família R$294,20, SECCO R$164,36, Sergio R$65,90 na cópia | Preservar por cartão e mês; não somar fotografias antigas de fatura. Dados posteriores a 12/10 podem estar ausentes. |
| Caixinhas | Mercado Pago R$0 observado em 11/10 com resgate não apurado; Nubank R$5.262,23 apenas em setembro | Não incorporar ao saldo livre de 19/10 nem inferir resgate/rendimento. Preservar aporte de R$800 em 06/10. |
| Benefício, seguros e gastos incertos | Nenhum saldo atual confirmado de auxílio-transporte; academia/internet/Uber e proteção veicular não confirmados | Não criar pagamento ou crédito. Manter pendências explícitas de conferência. |
| Banco | Migration `0012_classe_despesa` aplicada; Foundation V3 presente, sem contas financeiras da titular | Acrescentar somente a data opcional de abatimento contratual na migration `0013_abatimento_compromisso`. |

O saldo de R$668,96 **já reflete o que aconteceu até a referência informada**. O salário recebido, a entrada da Hunter, equipamentos e Pix não são somados ou subtraídos novamente para alcançá-lo. Os R$1.970 previstos elevam o cenário *antes de novas saídas* a R$2.638,96; a previsão final subtrai obrigações ainda pendentes pelo serviço de planejamento.

O cancelamento do CDC Protegido tem crédito nominal identificado de R$1.236,16 nas duas parcelas. O destino dos R$251,84 restantes é desconhecido; não virou caixa, receita nem rendimento. O reembolso Mão na Roda é separado do CDC Protegido e ainda não foi recebido. Não há pagamento nem cotação atual de antecipação das parcelas finais.

## Resultado na cópia local

- `FinancialAccount` de reconciliação temporária, com único saldo observado de **R$668,96 em 19/10**, anotando a composição R$418,96 + R$250 sem atribuição bancária. O snapshot antigo de R$684,39 permanece histórico. O planejamento passa a usar a conta agregada, sem somá-la aos ativos antigos.
- Transação prevista `936` e compromisso salarial `15` movidos de 15 para **20/10**. Transação prevista `937` de R$700 preservada. Recebível pontual de **R$550 até 28/10** criado na categoria “Reembolsos e estornos”. São **R$1.970 pendentes**, não recebidos.
- Compromisso Hunter `7` preserva 48 parcelas de R$618,08; vencimentos ajustados para o dia 12. Ocorrências 01/48 e 02/48 foram registradas como **abatidas em 15/10 pelo credor**, sem `Transaction` nem `InvoicePayment`. A próxima obrigação é **03/48, 12/01/2027**. O valor financiado informativo foi atualizado para R$16.469,24; nenhum crédito de R$251,84 foi inferido.
- O cenário “Hunter — Antecipações de outubro/2026” foi salvo sem itens, pagamentos ou movimentações. A simulação na aba Contas é somente cálculo local.
- Pendências de conferência foram abertas ou atualizadas para documentação de R$904 em 4×R$226, academia/internet, auxílio-transporte restrito, diferença do CDC e confirmação dos recebimentos. Não foram criadas parcelas de cartão nem pagamentos com origem ou vencimento desconhecidos.

Na cópia, **não há obrigação de outubro confirmada ainda em aberto**. Portanto, o cálculo do planejamento retorna R$2.638,96 após as três entradas e antes de novas saídas confirmadas. Esse valor é **parcial, não um teto seguro de gastos ou antecipações**: academia, internet, dentista, documentação e possíveis diferenças posteriores ao backup ainda exigem conferência. Em novembro e dezembro a Hunter contribui R$0 ao total pendente; em janeiro, R$618,08.

## Limites do ensaio

O ensaio não atribui R$418,96 ou R$250 a Nubank, Mercado Pago ou carteira. O valor da documentação permanece fora da fatura até cartão e vencimento serem confirmados. Não presume pagamento de academia, internet, dentista ou proteção veicular. O histórico de saldo e investimentos é mantido, inclusive o aporte de R$800. A atualização em produção depende de backup atual, comparação de diferenças e aprovação específica.

Ainda faltam confirmação ou origem para: pagamento de academia (R$120) e internet (R$60); dentista (R$112 de referência), Uber anterior (R$80 incerto), cartão e primeiro vencimento da documentação, composição bancária dos R$668,96, resgate das Caixinhas, crédito do auxílio-transporte restrito e destino dos R$251,84 do CDC. A viagem de R$350 está cancelada; o consórcio de R$479,38 era proposta; manutenção de R$50/mês e proteção Primos de aproximadamente R$94 são estimativas, sem pagamento. Nenhum desses valores foi usado para forçar o saldo observado.

A simulação local reserva os pagamentos e provisões **registrados** antes de mostrar o efeito de antecipar R$200, R$500, R$800, R$1.000 ou um valor livre. Como as obrigações incompletas não têm valor confirmado, ela não apresenta um “máximo seguro”. Com gasto extra zero e sem obrigação confirmada pendente em outubro na cópia, os saldos após antecipação seriam:

| Antecipação | Hoje: R$668,96 | Após R$700 + R$720: R$2.088,96 | Após mais R$550: R$2.638,96 |
| ---: | ---: | ---: | ---: |
| R$200 | R$468,96 | R$1.888,96 | R$2.438,96 |
| R$500 | R$168,96 | R$1.588,96 | R$2.138,96 |
| R$800 | −R$131,04 | R$1.288,96 | R$1.838,96 |
| R$1.000 | −R$331,04 | R$1.088,96 | R$1.638,96 |

Os R$700, R$720 e R$550 só entram nos cenários condicionais; a simulação não marca recebimento nem cria antecipação. A cotação histórica de R$167,55 para a parcela final não foi usada como pagamento ou desconto atual.
