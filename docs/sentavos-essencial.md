# Sentavos Essencial

## Estado da integração

O Essencial é a aplicação principal autenticada. As cinco áreas usam React Query, os endpoints e as regras financeiras existentes. `/essencial.html` leva à aplicação principal; o protótipo de memória foi arquivado como [registro das fases 1 e 2](sentavos-essencial/prototipo-fases-1-2.md). A reconciliação de 19/10 foi ensaiada somente em cópia PostgreSQL local e está documentada em [outubro de 2026](sentavos-essencial-reconciliacao-2026-10.md). Não houve escrita em produção nem publicação nesta etapa.

| Antes | Agora |
| --- | --- |
| Início priorizava o resultado e os gráficos do mês | Meu mês mostra o dinheiro conhecido, a previsão e o que falta receber/pagar |
| Cinco abas, com planejamento e patrimônio no primeiro nível | Meu mês, Lançamentos, Contas, Relatórios e Investir; funções avançadas ficam em links e Configurações |
| Lançar começava por tipo, descrição e muitos campos | `+` abre valor, conta/cartão, categoria e Salvar; detalhes opcionais ficam recolhidos |
| Planejamento exigia navegar por resultados e listas | Meu mês usa o cálculo do servidor, abre os detalhes sob demanda e mostra três meses seguintes |
| Gráficos apareciam na entrada do app | Distribuição e evolução ficam em Relatórios; Investir começa pelos saldos conhecidos |

## Navegação e tarefas

- `/`: Meu mês. Mostra saldo conhecido nas contas livres ou saldo agregado reconciliado, com data/qualidade; a previsão usa `GET /planning/month` e separa saídas estimadas ainda a conferir. O detalhe do cálculo mostra esse ajuste. A linha A pagar abre as obrigações confirmadas. Entradas, despesas fixas, variáveis e investimentos aparecem em quatro linhas compactas; cada detalhe abre sob demanda. Pagamentos já feitos vêm dos lançamentos; pendências vêm do planejamento. Faturas são caixa, compras continuam gasto por competência e aportes planejados continuam reservas. Com pendências de conciliação, a projeção fica marcada como parcial.
- `/lancamentos`: lista cronológica de lançamentos e pagamentos de fatura, filtros simples, edição e `+` global. Compras parceladas abrem o editor próprio. O atalho de lançamento sugere a última conta válida, data de hoje, despesa e finalidade Pessoal; evita salvamento repetido e invalida os resumos após sucesso.
- `/contas-a-pagar`: separa A pagar, A conferir e Já pagas no mês selecionado, além do cronograma de abatimentos da Hunter e próximos vencimentos. O total A pagar usa apenas obrigações confirmadas e deduplicadas do planejamento; cotações e parcelas sem primeira data ficam fora do total. Já pagas usa pagamentos efetivos de fatura no mês, inclusive parciais, baixas de compromissos e despesas fixas avulsas sem duplicá-los. Uma conta a conferir pode ser vinculada a pagamento existente, registrada como paga com conta de origem ou transformada em compromisso com vencimento confirmado. Parcelamentos sem dados suficientes pedem conferência das parcelas antes de criar caixa ou fatura. A API recusa uma segunda criação sobre o mesmo item; quando um vínculo antigo foi apagado, o item precisa ser reaberto em Conferir mês antes de criar outro registro. Faturas abrem a tela de faturas; lançamentos previstos abrem Lançamentos. A simulação de antecipação separa saldo atual, primeiras entradas e todas as entradas, reserva obrigações conhecidas e não grava transações. A antiga `/contas` continua administrando contas bancárias nas Configurações.
- `/relatorios`: entrou, gastou, investiu e resultado de caixa, com definições explícitas. Rosca por categoria, evolução de 6/12 meses, finalidade e custo de vida usam agregações existentes. Resultado de caixa pendente de conciliação aparece como “A conferir”.
- `/investimentos`: saldo conhecido primeiro, depois ativos e seus saldos, aportes, resgates e rendimento. Quando um saldo antigo impedir o total atual, a tela marca a ausência. Rendimento sem base confiável aparece como “Não apurado”. Patrimônio completo permanece acessível.
- `/planejamento/proximos`: comparação real de meses calculados em sequência no backend. Desktop apresenta linhas lado a lado; mobile usa blocos compactos, sem tabela larga obrigatória. Fixas incluem faturas; variáveis incluem despesas ainda sem classificação. A linha final usa `available`, após reservas.

O planejamento detalhado, orçamento e metas, cartões/faturas, compromissos/recorrências, provisões, simulações salvas, contas, conferência, reconciliação, patrimônio, categorias e perfil continuam nas rotas atuais, nos links contextuais e em Configurações. `/transacoes` e `/orcamento?aba=lancamentos` redirecionam para a lista nova; `/categorias` abre a seção de categorias. Faturas continuam em `/orcamento?aba=faturas`.

## Domínio e banco

A migration `0012_classe_despesa` adiciona `expense_class` opcional a lançamentos, compras e compromissos. Nenhuma linha histórica é reclassificada. Um compromisso sem escolha explícita sugere “fixa”; uma baixa pode receber exceção manual. Compras copiam a classificação para todas as parcelas, inclusive após editar o rótulo. A classificação organiza a leitura; não altera caixa, gasto, investimento, natureza nem fatura. A migration verifica colunas existentes porque a migration inicial cria o modelo atual em bancos vazios; o downgrade remove apenas as três colunas.

`FinancialAccount` é usado quando já existe. Na cópia de validação, o saldo agregado de R$668,96 observado em 19/10 está numa conta temporária de reconciliação, sem inventar divisão por banco; o snapshot legado de R$684,39 permanece histórico. Saldos de investimento antigos não se tornam saldo atual. A previsão continua usando o serviço de planejamento. A simulação de antecipação calcula variações sobre essa previsão sem criar fonte de verdade nem pagamento.

A migration `0013_abatimento_compromisso` acrescenta data opcional de abatimento em `CommitmentSkip`. `abatida` é estado distinto de `paga` e `dispensada`; não cria saída de caixa e sai das obrigações futuras. As rotas de pagar, dispensar e desfazer dispensa recusam alterar uma parcela abatida por acidente.

A logo original permanece intacta. Os PNGs do cabeçalho, login, favicon, ícones PWA e Apple touch icon têm o mesmo hash da branch `main`. Apenas a cor de fundo do manifesto e o tema acompanham a paleta atual.

## Validação local

Os testes de backend usam SQLite isolado. As migrations foram ensaiadas em PostgreSQL local vazio e em cópia dos backups disponíveis nesta máquina, datados de 12/10/2026. O downgrade/upgrade de `0013` passou no banco vazio. A validação de navegador usa a cópia local reconciliada; como os bancos de origem ainda são desconhecidos, o teste escolhe explicitamente “Conta ainda não informada” para o Pix e o aporte, sem atribuir uma instituição fictícia. A conta demo continua somente leitura. Essas cópias não confirmam o estado atual da produção.

Comandos principais:

```powershell
uv run --with pgserver python -m scripts.postgres_local start
$env:APP_ENV='development'
$env:DATABASE_URL='postgresql://postgres@127.0.0.1:54329/sentavos_dev'
$env:SENTAVOS_JWT_SECRET='<segredo-local>'
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```powershell
cd frontend
$env:VITE_API_URL='http://127.0.0.1:8000'
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

Abrir `http://127.0.0.1:5173/`. Para os testes locais: `python -m pytest -q -p no:cacheprovider`, `npm.cmd run lint`, `npm.cmd run build`, `npm.cmd run test:essencial` (sete verificações de modelo preservadas) e `npm.cmd run test:integrated` com API e frontend apontados a uma cópia local. A configuração E2E aceita `SENTAVOS_E2E_API`, `SENTAVOS_E2E_WEB`, `SENTAVOS_E2E_EMAIL`, `SENTAVOS_E2E_DEMO_EMAIL` e `SENTAVOS_E2E_PASSWORD`. Na API de teste, usar `RATE_LIMIT_POR_MINUTO=10000`: a navegação automatizada abre todas as telas em sequência e ultrapassa a cota normal de 240, que permanece intacta no aplicativo. O teste nunca deve apontar a produção: ele cria um saldo e lançamentos na base de validação.

As capturas das cinco telas com a cópia local ficam em `.local/essencial-review/`, fora do Git por conter dados financeiros. A revisão cobriu 320, 360, 400, 768 e 1440 px. O navegador automatizado verifica os caminhos, mas não comprova uma leitura humana em três segundos nem um lançamento humano em dez; esses tempos pedem uso observado no aparelho antes do rollout.

Resultado nesta branch: 516 testes de backend, sete verificações do modelo preservado e 15 cenários E2E integrados passaram; TypeScript, build de produção e revisão de overflow nas cinco larguras também passaram. A regressão financeira da cópia local apontou zero divergências antes de outubro de 2026.

## Pendências para publicação

Revisar a experiência em aparelho físico e com saldos atuais após conferir os dados da conta. A cópia disponível é de 12/10/2026 e contém uma caixinha sem saldo atualizado/rendimento apurado; a interface mostra essas limitações. Publicação, push para `main` e qualquer escrita em produção dependem de revisão posterior.
