# Sentavos Essencial — auditoria e protótipo de revisão

## Estado desta entrega

Fases 1 e 2: auditoria do código e protótipo navegável local. A integração definitiva vem depois da apresentação destas quatro telas, conforme a sequência solicitada. Não houve acesso ao banco de produção, importação, migration, alteração de registros, push ou deploy. A aplicação existente continua sendo a entrada padrão.

- Branch: `feat/sentavos-essencial`.
- Rodar: `cd frontend` e `npm.cmd run dev -- --host 127.0.0.1 --port 5179 --strictPort`.
- Abrir: `http://127.0.0.1:5179/essencial.html#/`.
- Quatro telas: `#/`, `#/lancamentos`, `#/relatorios`, `#/investir`.
- Comparação: `#/comparar`; cartões: `#/cartoes`.
- Data demonstrativa fixa: 18/10/2026. Todos os valores são fictícios e identificados.
- Lançamentos modificam somente a memória do protótipo. Recarregar restaura os exemplos.
- Build separado: `npm.cmd run build:essencial` → `dist-essencial/essencial.html`.
- O build padrão não inclui `essencial.html`. O protótipo não importa cliente HTTP, autenticação, hooks de API nem storage financeiro da aplicação.

A imagem da planilha não foi localizada entre os arquivos fornecidos nesta sessão. A referência funcional foi a descrição detalhada do pedido; nenhuma imagem foi inventada ou presumida.

### Apresentação das quatro telas

| Tela | Abrir protótipo | Captura revisada |
|---|---|---|
| Meu mês | [Navegar](http://127.0.0.1:5179/essencial.html#/) | [Primeira dobra 400px](sentavos-essencial/primeira-dobra-400.png) · [360px](sentavos-essencial/primeira-dobra-360.png) · [Desktop](sentavos-essencial/meu-mes-1440.png) |
| Lançamentos | [Navegar](http://127.0.0.1:5179/essencial.html#/lancamentos) | [Lista](sentavos-essencial/lancamentos-400.png) · [Lançamento rápido](sentavos-essencial/lancamento-rapido-400.png) |
| Relatórios | [Navegar](http://127.0.0.1:5179/essencial.html#/relatorios) | [Ver captura](sentavos-essencial/relatorios-400.png) |
| Investir | [Navegar](http://127.0.0.1:5179/essencial.html#/investir) | [Ver captura](sentavos-essencial/investir-400.png) |

[Comparação de meses no desktop](sentavos-essencial/comparar-1440.png). Capturas são do protótipo com dados fictícios, não da conta real.

## Fase 1 — o que existe

| Área | Situação encontrada | Evolução proposta |
|---|---|---|
| Navegação | Cinco abas: Início, Lançamentos, Planejamento, Investir, Patrimônio | Quatro abas, com planejamento essencial em Meu mês e patrimônio secundário |
| Início (`Dashboard.tsx`) | Primeiro número é resultado de caixa do mês; contém distribuição, evolução, faturas e recentes | Dinheiro conhecido e previsão primeiro; gráficos em Relatórios |
| Lançamentos (`Budget.tsx`) | Destino inicial abre Orçamento; lista e faturas são subabas | Lista como destino principal, faturas secundárias e orçamento acessível em configurações |
| Formulário (`TransactionForm.tsx`) | Começa por tipo e descrição; categoria, data, pagamento, conta, finalidade, natureza, previsto/pago e observação competem | Valor → conta → categoria → salvar; detalhes recolhidos |
| Planejamento | Domínio e APIs de mês, horizonte, reservas, compromissos e simulação avulsa já implementados | Reutilizar, sem nova fórmula no frontend integrado |
| Contas | Foundation V3 presente: `FinancialAccount`, saldo observado, movimentos posteriores, qualidade, restrição e conta agregada | Reutilizar. Nenhuma nova tabela de conta necessária |
| Investimentos | Movimentos tipados e resumo por ativo, rendimento apurado/não apurado, valores antigos sinalizados | Saldo conhecido e lista por ativo; composição e CDI saem da primeira camada |
| Fixas/variáveis | Há vínculo a compromisso e natureza analítica; não há classificação explícita fixa/variável | Campo opcional próprio; não confundir recorrência com previsibilidade ou Nature com fixa/variável |
| Configurações | Contas, cadastro de cartões, categorias, CDI e perfil na mesma página longa | Grupos Financeiro, Dados e Conta; administração acessível sob demanda |
| Design | Base V2 já tem tokens, listas, grafite e números tabulares; hierarquia de produto ainda complexa | Consolidar componentes após revisão do protótipo; evitar substituir tokens globais antes disso |

Fontes: `frontend/src/App.tsx`, `components/Layout.tsx`, páginas acima, `lib/queries.ts`, `lib/tiposContas.ts`, `lib/tiposPlanejamento.ts`, `app/models.py`, `app/dominio/`, `app/planejamento.py` e `docs/financial-domain.md`.

### Contratos a reutilizar na integração

| Necessidade | Contrato/hook existente | Cuidado |
|---|---|---|
| Dinheiro conhecido | `useAccountsSummary`, `useAccounts`, `accountsApi.summary` | Respeitar `include_in_planning`, `restricted`, `to_distribute`, qualidade e avisos; sem inventar distribuição por banco |
| Previsão do mês | `usePlanningMonth`, `GET /planning/month` | Usar `projected` e `available` do servidor; `available` já considera reservas |
| Meses seguintes | `usePlanningHorizon`, `GET /planning/horizon` | Saldo final alimenta mês seguinte. Mês corrente mostra pendências, não o total histórico |
| Gasto adicional sem gravar | `useSimular`, `POST /planning/simulate` | Endpoint calcula sem persistir cenário ou transação |
| Lançamentos e categorias | `useTransactions`, `useCategories`, `useCreateTransaction` | Data/instante, dono, forma de pagamento e categoria válidos |
| Compra parcelada | `useCreatePurchase` | API decide competência, fatura e arredondamento. Não transportar o modelo demonstrativo para produção |
| Cartões/faturas | `useCards`, `useInvoicesSummary` e fluxos de `Invoices.tsx` | Preservar baixa parcial, origem do pagamento e reconciliação |
| Dinheiro guardado | `useInvestmentSummary`, `useInvestmentMovements`, `useCreateMovement` | Resgate não é receita comum; não afirmar rendimento sem base conciliada |
| Relatórios | `useCategoryReport`, `useMonthlyReport`, `useBudgetSummary` | Distinguir gasto de competência, saída de caixa e resultado |
| Qualidade dos dados | `useMonthHealth` | Aviso discreto sem bloquear as outras tarefas |

### Regras que orientam a experiência

1. Dinheiro em conta é saldo observado + movimentos posteriores elegíveis. Não é receita nem resultado do mês.
2. Previsão de caixa = saldo de partida + recebimentos futuros − obrigações de caixa futuras − aportes + resgates.
3. Valor livre = previsão de caixa − reservas ainda aplicáveis. Reserva não é gasto nem saída real.
4. Despesa à vista paga já está no saldo; não subtrair de novo.
5. Compra de cartão é gasto por competência. Fatura paga é caixa; não entra outra vez no gasto total.
6. Investimentos mudam a alocação do dinheiro. Rendimento exige base suficiente.
7. Saldo sem informação não é zero comprovado. Saldo antigo é identificado. Agregado a distribuir não se soma novamente ao ser distribuído.
8. Mês encerrado usa dados históricos; nunca atribuir o saldo conhecido hoje a outubro passado. O protótipo explicita o contexto e mantém o número de hoje separado.
9. Multiusuário, demo read-only e controles do backend continuam obrigatórios na integração. O sandbox fictício desta entrega é independente da conta demo do produto.

## Fase 2 — arquitetura e experiência proposta

```text
Meu mês (inicial)
  Dinheiro agora → Contas e saldos
  Previsão → Detalhe do cálculo
  E se eu gastar? → Simulação sem gravar
  Entradas / Fixas / Variáveis / Investimentos → Expandir
  Planejamento → Lista das pendências
  Cartões → Faturas
  Próximos meses → Comparação
Lançamentos
  Lista cronológica → Detalhe e correção fixa/variável
  Todos / Entradas / Despesas / Investimentos
  Filtros adicionais recolhidos
Relatórios
  Resultado de receitas e gastos + resumo do mês
  Finalidade e custo de vida → Filtros dos gráficos
  Categorias + evolução; valores acessíveis em lista
Investir
  Total conhecido → Lista por investimento
  Aportar / Resgatar → Mesmo formulário adaptado
  Movimentações do mês; rendimento não apurado quando aplicável
  Patrimônio completo (secundário)
Configurações (fora das quatro abas)
  Financeiro: Contas, Cartões, Categorias, Recorrências, Patrimônio, Orçamento
  Dados: Conferir mês, Histórico, Simulações salvas
  Conta: Perfil e Sair (na integração com autenticação)
```

No desktop, a lateral usa as mesmas quatro abas; acessos secundários ficam abaixo de um divisor. No celular, barra inferior de quatro posições e ação `+` acima dela.

### Antes × proposta

| Antes | Protótipo |
|---|---|
| Resultado do mês como número principal | Dinheiro conhecido agora, com datas visíveis |
| Planejamento como quinta tarefa principal | Previsão na primeira dobra de Meu mês |
| Gráficos no Início | Gráficos concentrados em Relatórios |
| Lista atrás da subaba Orçamento | Lançamentos abre a lista |
| Descrição obrigatória antes do valor | Valor primeiro; descrição opcional, derivada da categoria |
| Muitos campos cotidianos | Conta e categoria; data, finalidade e organização em detalhes |
| Patrimônio como aba | Investir começa pelo guardado; patrimônio secundário |
| Configurações longas | Assuntos agrupados |
| Meses em telas separadas | Comparação desktop lado a lado; mobile em blocos legíveis sem tabela larga |

### Meu mês

Dinheiro conhecido é independente do resultado mensal. A data dos saldos é visível. A previsão mostra o livre depois das contas, aportes previstos e reservas, com o cálculo completo por toque. A receber e a pagar abrem as pendências. Investido leva a Investir. Cada grupo exibe até três movimentos e permite expandir. As faturas ficam em uma linha própria para não duplicar compras nas despesas. Dois meses seguintes levam diretamente aos compromissos.

### Lançamento rápido

`+` → valor (foco imediato, teclado decimal) → conta anterior validada entre as opções → categoria → salvar. Data padrão é o dia demonstrativo e finalidade Pessoal. Descrição vem da categoria quando não informada. Campos secundários ficam recolhidos. Categoria frequente pode ser escolhida por botão.

Cartão oferece parcelas e explica a prévia. O protótipo cria parcelas/faturas somente em memória, com regra demonstrativa de vencimento no mês seguinte; isso não é um contrato novo para o produto. Na integração, o fluxo de compra existente será obrigatório.

Aporte/resgate mostra conta de origem/destino e investimento. O resgate não entra como receita comum; aporte não entra como gasto. O protótipo impede resgate maior que o saldo demonstrativo conhecido. Datas históricas/baixas/transferências completas ficam para os fluxos reais existentes, sem fingir que estão integradas.

### Comparação

Desktop: três meses por coluna, com saldo inicial, recebimentos, fixas, variáveis, faturas, aportes/resgates, saldo final e reservas. Mobile: os mesmos campos em blocos por mês. O primeiro mês pode ser selecionado. Outubro compara apenas o que ainda falta ocorrer; isso está explicado, evitando comparar resultado histórico com previsão restante como se fossem a mesma métrica.

### Relatórios e Investir

Relatórios define resultado como receitas recebidas menos gastos por competência. O resumo é do mês completo; finalidade e leitura custo de vida filtram os dois gráficos, com explicação explícita desse escopo. Não mistura aportes com despesas ou resgates com receitas. Percentuais têm o gasto filtrado como denominador. Sem registros não é desenhado como zero na linha.

Investir prioriza o total conhecido e lista das caixinhas. Mostra data dos valores, aporte, resgate e rendimento. Um ativo desatualizado fica fora do total, visível em detalhes. Movimentos novos são identificados como saldo observado + movimentações; não simulam rendimento. Patrimônio completo fica secundário.

### Componentes

Não foram apagados componentes do produto atual nesta fase. No protótipo, foram simplificados ou substituídos: hero de resultado, indicadores coloridos, hierarquia de abas/subabas, formulário extenso, visualização extensa do planejamento e entrada de patrimônio. Componentes compartilhados entre as quatro telas: `Summary`, `EntryRow`, `EntryGroup`, `SectionHeading`, `MonthControl`, `Sheet`, `Calculation`, `QuickSheet` e navegação. Cores, tipografia, raio, estados e controles estão centralizados em `src/essencial/styles.css`.

## Fase 3 — plano de integração após apresentar a experiência

1. Promover shell e tokens revisados, mantendo a autenticação atual e o bloqueio read-only.
2. Meu mês usa os resultados de contas/planejamento do servidor, sem copiar o calculador demonstrativo. Carregamento, erro, ausência de saldo, saldo parcial, restrições e dados antigos precisam de estados reais próprios.
3. Lançamentos reutiliza lista/edição, cria formulário rápido com defaults válidos e reaproveita operações de compra e investimento.
4. Relatórios recebe os gráficos e filtros atuais. Investir recebe o resumo existente e mantém rotas de patrimônio.
5. Configurações agrupa links para fluxos completos existentes. Nada de remover funcionalidades.
6. Compatibilidade proposta: `/` → Meu mês; `/lancamentos` → lista; `/relatorios` → análise; `/investimentos` permanece Investir. `/orcamento?aba=lancamentos` e `/transacoes` redirecionam preservando `novo=1`; `/orcamento?aba=faturas` continua abrindo faturas; orçamento/metas tem destino secundário explícito. `/planejamento`, `/planejamento/proximos`, `/planejamento/simulacoes`, `/planejamento/compromissos`, `/organizar`, `/contas`, `/rever`, `/patrimonio` e `/configuracoes` continuam funcionando. Confirmar regressão de parâmetros e links antes de trocar rotas.

## Fase 4 — menor evolução de domínio proposta, não executada

Não é necessário recriar Foundation V3. Também não é correto inferir fixa/variável pela natureza analítica ou pelo nome da categoria.

Proposta a detalhar antes da integração: classificação opcional `expense_class` (`fixed`/`variable`) em lançamento e compromisso, copiada na baixa. Categoria pode fornecer sugestão apenas se necessário, sem duplicar categorias. Precedência: escolha explícita → compromisso vinculado → sugestão. Histórico sem classificação deve ser identificado como “A confirmar”, com correção manual; não reclassificar silenciosamente todos os registros. Compra/parcelas exigem decisão sobre a origem da classificação para manter todas as parcelas consistentes.

A migration futura deve ser aditiva, inicialmente nullable e sem inferência destrutiva de dados reais. Documentar upgrade/downgrade, ensaiar em PostgreSQL real vazio e em cópia segura, verificar valores financeiros antes/depois, isolamento e compatibilidade com o frontend antigo. Nenhuma migration foi criada nesta entrega.

## Fases 5 e 6 — validação e publicação

### Verificação desta etapa

| Verificação | Resultado e alcance |
|---|---|
| Backend e domínio financeiro | `python -m pytest -q -p no:cacheprovider`: 510 testes passaram, com uma advertência de depreciação da dependência Starlette/httpx. Banco de teste isolado; nenhum teste contra produção |
| TypeScript | `tsc --noEmit` passou, também executado pelos builds |
| Build padrão | `npm.cmd run build` passou; `dist/essencial.html` não existe |
| Build de revisão | `npm.cmd run build:essencial` passou; saída separada em `dist-essencial/` |
| Testes novos | `npm.cmd run test:essencial`: 23 verificações (7 de modelo e 16 de experiência/layout) |
| Tarefas 1–7 | Caminhos exercitados no navegador com dados fictícios, incluindo leitura, simulação, Pix, novembro, caixinhas, categorias e comparação |
| Integridade demonstrativa | Centavos, despesas pagas fora das pendências, saldo transportado antes de reservas, aportes/resgates separados de receita/gasto, parcelas e faturas sem duplicação |
| Responsividade | Edge headless: 320×800, 360×800, 400×860, 768×1024 e 1440×1000; quatro telas e comparação sem overflow horizontal |
| Acessibilidade exercitada | Foco inicial no valor, Escape, retorno ao acionador, rótulo da classificação, elementos semânticos e redução de movimento implementada |
| Revisão visual | Capturas de Meu mês, lançamento rápido, Lançamentos, Relatórios, Investir e comparação inspecionadas |
| API/produção | Nenhum acesso financeiro pelo protótipo; simulação e lançamentos são locais à memória |

Na primeira execução, os testes apontaram falta do total de contas no topo do planejamento. O total foi incluído e a fórmula passou para detalhes. Foram corrigidos seletores ambíguos de teste, o rótulo acessível da classificação e a configuração do Vite para não observar diretórios gerados; isso evita conflito de arquivos no Windows. A revisão visual também removeu o botão flutuante de telas analíticas e eliminou o segundo seletor de mês na comparação.

Os testes de tarefa do protótipo verificam o caminho e os cálculos demonstrativos. Não medem a compreensão humana em três segundos nem comprovam lançamento humano em dez segundos. Isso exige uso observado pelo criador, seguido por validação com APIs reais, cópia segura e estados incompletos.

Publicação só depois da integração, regressões, ensaio de qualquer migration e aprovação expressa. Esta entrega não configura deploy, não envia branch e não escreve em produção.

## Pendências de produto reais

- Revisar as quatro telas demonstrativas antes da integração definitiva.
- Integrar as APIs e preservar todos os fluxos avançados e deep links.
- Definir/ensaiar a classificação de fixas/variáveis; o campo demonstrativo não altera o modelo real.
- Validar contas restritas, saldo a distribuir, contas sem saldo e saldos antigos com dados reais seguros.
- Validar baixa parcial, faturas, parcelas e financiamento real, além da prévia fictícia.
- Validar carregamento/erro/offline e demo read-only na interface integrada.
- Observar as sete tarefas com o usuário; acessibilidade assistiva e testes em aparelho físico.
- Aprovação e publicação são etapas posteriores.
