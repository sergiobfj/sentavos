# Sentavos Essencial

## Estado da integração

O Essencial é a aplicação principal autenticada. As quatro áreas usam React Query, os endpoints e as regras financeiras existentes. `/essencial.html` leva à aplicação principal; o protótipo de memória foi arquivado como [registro das fases 1 e 2](sentavos-essencial/prototipo-fases-1-2.md). Não houve escrita em produção, push ou publicação.

| Antes | Agora |
| --- | --- |
| Início priorizava o resultado e os gráficos do mês | Meu mês mostra o dinheiro conhecido, a previsão e o que falta receber/pagar |
| Cinco abas, com planejamento e patrimônio no primeiro nível | Meu mês, Lançamentos, Relatórios e Investir; funções avançadas ficam em links e Configurações |
| Lançar começava por tipo, descrição e muitos campos | `+` abre valor, conta/cartão, categoria e Salvar; detalhes opcionais ficam recolhidos |
| Planejamento exigia navegar por resultados e listas | Meu mês usa o cálculo do servidor, abre os detalhes sob demanda e mostra três meses seguintes |
| Gráficos apareciam na entrada do app | Distribuição e evolução ficam em Relatórios; Investir começa pelos saldos conhecidos |

## Navegação e tarefas

- `/`: Meu mês. Mostra saldo conhecido nas contas livres ou saldo agregado legado, com data/qualidade; previsão vem de `GET /planning/month`. A linha A pagar abre as obrigações. Entradas, despesas fixas, variáveis e investimentos mostram até três itens inicialmente. Pagamentos já feitos vêm dos lançamentos; pendências vêm do planejamento. Faturas são caixa, compras continuam gasto por competência e aportes planejados continuam reservas.
- `/lancamentos`: lista cronológica de lançamentos e pagamentos de fatura, filtros simples, edição e `+` global. Compras parceladas abrem o editor próprio. O atalho de lançamento sugere a última conta válida, data de hoje, despesa e finalidade Pessoal; evita salvamento repetido e invalida os resumos após sucesso.
- `/relatorios`: entrou, gastou, investiu e resultado de caixa, com definições explícitas. Rosca por categoria, evolução de 6/12 meses, finalidade e custo de vida usam agregações existentes. Resultado de caixa pendente de conciliação aparece como “A conferir”.
- `/investimentos`: saldo conhecido primeiro, depois ativos e seus saldos, aportes, resgates e rendimento. Quando um saldo antigo impedir o total atual, a tela marca a ausência. Rendimento sem base confiável aparece como “Não apurado”. Patrimônio completo permanece acessível.
- `/planejamento/proximos`: comparação real de meses calculados em sequência no backend. Desktop apresenta linhas lado a lado; mobile usa blocos compactos, sem tabela larga obrigatória. Fixas incluem faturas; variáveis incluem despesas ainda sem classificação. A linha final usa `available`, após reservas.

O planejamento detalhado, orçamento e metas, cartões/faturas, compromissos/recorrências, provisões, simulações salvas, contas, conferência, reconciliação, patrimônio, categorias e perfil continuam nas rotas atuais, nos links contextuais e em Configurações. `/transacoes` e `/orcamento?aba=lancamentos` redirecionam para a lista nova; `/categorias` abre a seção de categorias. Faturas continuam em `/orcamento?aba=faturas`.

## Domínio e banco

A migration `0012_classe_despesa` adiciona `expense_class` opcional a lançamentos, compras e compromissos. Nenhuma linha histórica é reclassificada. Um compromisso sem escolha explícita sugere “fixa”; uma baixa pode receber exceção manual. Compras copiam a classificação para todas as parcelas, inclusive após editar o rótulo. A classificação organiza a leitura; não altera caixa, gasto, investimento, natureza nem fatura. A migration verifica colunas existentes porque a migration inicial cria o modelo atual em bancos vazios; o downgrade remove apenas as três colunas.

`FinancialAccount` é usado quando já existe. A conta histórica da cópia de validação ainda tem saldo agregado legado: a tela apresenta esse saldo com a data observada, sem inventar divisão por banco. Saldos de investimento antigos não se tornam saldo atual. A previsão e a simulação continuam usando os serviços de planejamento; a interface não mantém uma segunda fórmula.

A logo original permanece intacta. Os PNGs do cabeçalho, login, favicon, ícones PWA e Apple touch icon têm o mesmo hash da branch `main`. Apenas a cor de fundo do manifesto e o tema acompanham a paleta atual.

## Validação local

Os testes de backend usam SQLite isolado. O ensaio de migration usou PostgreSQL local vazio e uma cópia dos backups mais recentes disponíveis nesta máquina, datados de 12/10/2026: 536 lançamentos, 27 compras e 10 compromissos. A nova coluna ficou nula no histórico e os valores de todas essas linhas permaneceram idênticos. O ensaio de downgrade/upgrade também passou. A validação de navegador usa outra cópia local, com uma conta de teste criada somente nessa base para exercer Pix e edição; a conta demo continua somente leitura. Essas cópias não confirmam saldos de produção em 19/10/2026.

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

As capturas das quatro telas com a cópia local ficam em `.local/essencial-review/`, fora do Git por conter dados financeiros. A revisão cobriu 320, 360, 400, 768 e 1440 px. O navegador automatizado verifica os caminhos, mas não comprova uma leitura humana em três segundos nem um lançamento humano em dez; esses tempos pedem uso observado no aparelho antes do rollout.

## Pendências para publicação

Revisar a experiência em aparelho físico e com saldos atuais após conferir os dados da conta. A cópia disponível é de 12/10/2026 e contém uma caixinha sem saldo atualizado/rendimento apurado; a interface mostra essas limitações. Publicação, push para `main` e qualquer escrita em produção dependem de revisão posterior.
