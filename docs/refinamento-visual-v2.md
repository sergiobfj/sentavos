# Refinamento visual V2

Implementado a partir de `origin/main` (`622c783`), na branch `feat/refinamento-visual-v2`.
Revisão feita no aplicativo React existente, com API e PostgreSQL locais e dados
sintéticos. As capturas antes/depois usam o mesmo usuário de teste.

O complemento mais recente, descrito ao final, está nas capturas de
`refinamento-visual-v2/complemento/`. As imagens da primeira rodada foram preservadas.

## Identidade e componentes

- Fundo `#101319`, superfícies `#1C222D` / `#252C38`, bordas `#343C4B`.
- Texto `#F3F5F9`, secundário `#A4ADBB`; texto discreto `#98A3B4` para contraste.
- Ação `#A79AF5`, positivo `#67C7A2`, atenção `#E9B875`, negativo `#ED9195`.
- Tokens centralizados em `frontend/src/index.css`; removidas as duas paletas
  sobrepostas em `product.css`. Variáveis de acento substituem os nomes de dourado.
- Logo original intacta, apresentada em branco por CSS. Sem alteração de geometria.
- Campos, foco, botões, separadores e estados compartilham a mesma paleta.
- Navegação com superfície mais leve, ícone ativo discreto, alvos de pelo menos
  44px de altura e reserva de conteúdo com `safe-area-inset-*`.

## Lançamentos e Contas

Lançamentos: resumo compacto, quatro filtros visíveis, agrupamento por dia,
descrição prioritária, contexto secundário e valor à direita. Estados pendentes
usam atenção; entradas recebidas usam positivo. Compra no cartão mantém “No cartão”.
Edição continua no toque da linha; exclusão mantém confirmação. Links auxiliares
ficam em “Mais opções”. O formulário rápido foi preservado.

Contas: cabeçalho próximo dos indicadores, maior destaque para A pagar e grupos
com linhas compactas. A conferir mostra quantidade de itens, mantendo o valor
mensal conhecido como informação secundária quando existe. Valores desconhecidos
mostram “A confirmar”; cotações e parcelamentos sem data têm identificação própria.
Nenhum total financeiro foi recalculado por esta mudança.

Meu mês mantém a estrutura e os cálculos. Relatórios e Investir mantêm organização
e funcionalidades, incluindo a separação entre previsão e realização.

## Capturas

| Tela, 400px | Antes | Depois |
| --- | --- | --- |
| Lançamentos | [Antes](refinamento-visual-v2/lancamentos-antes-400.png) | [Depois](refinamento-visual-v2/lancamentos-depois-400.png) |
| Contas | [Antes](refinamento-visual-v2/contas-antes-400.png) | [Depois](refinamento-visual-v2/contas-depois-400.png) |

A pasta também inclui antes/depois em 360px, resultados em 320/768/1440px e as
outras três áreas e o formulário em 400px.

## Validação

- TypeScript (`npm run lint`) e build de produção aprovados.
- 12 E2E visuais: cinco áreas nas larguras 320/360/400/768/1440, formulário em
  viewport baixa, navegação, filtros, datas, detalhes de compra/fatura/pendência,
  estados vazios, 24 registros com nomes longos e valores de R$ 9.999.999,99,
  criação/edição/exclusão de previsão e contraste AA dos tokens de texto/estados.
- Sem overflow horizontal, valores cortados ou erros de console/HTTP nos percursos
  das cinco áreas. Último conteúdo alcançável acima da navegação ao fim da rolagem.
- 7 testes de modelo e 5 E2E existentes de previsões aprovados: aporte, edição,
  confirmação idempotente/concorrente, cancelamento, cartão e demonstração.
- Backend, contratos, migrações e regras financeiras não foram modificados;
  suíte de backend não foi necessária.

Para repetir, com o Postgres local e a API de testes na porta 8014 ativos:

```powershell
# Na raiz: cria outro usuário sintético e registra o estado visual atual.
.venv/Scripts/python.exe frontend/tests/visual/prepare.py
node frontend/tests/visual/capture.cjs seed
# Frontend em 5184 com VITE_API_URL=http://127.0.0.1:8014
cd frontend
npm run test:visual
```

## Conferência e limites

O pedido cita Seguro da Hunter e Proteção veicular por R$ 94. A fixture reproduz
uma obrigação e uma cotação, tornando essa diferença visível. Isso não confirma
se os registros reais são duplicados: conferir contratação, vigência e vínculo
antes de qualquer decisão financeira. Nenhum registro real foi consultado,
unido, excluído ou alterado.

Safe area validada pela implementação CSS e navegação em navegador; validação
em aparelho Android físico continua como conferência manual. Nenhuma publicação
ou alteração de produção foi feita.

## Complemento — revisão em 320, 400 e 768px

- Paleta e navegação inferior preservadas. Rótulos dos indicadores e textos
  secundários/status das linhas usam 12px; espaçamentos e altura mínima de 64px das linhas
  foram mantidos. Títulos não repetem o período já disponível no cabeçalho.
- “Já pagas” exibe despesas fixas quitadas e pagamentos vinculados a compromissos
  ou itens de conferência do tipo obrigação. Compras variáveis cotidianas permanecem
  em Lançamentos. A lista e seu indicador usam o mesmo recorte de apresentação.
- Faturas só aparecem como quitadas quando a API informa `paga`; pagamentos
  parciais continuam disponíveis em Lançamentos/Faturas, e o restante segue em
  A pagar. Abatimentos permanecem consultáveis em “Abatidas”, fora de Já pagas.
- Despesas variáveis previstas continuam em A pagar. Nenhum lançamento,
  classificação, saldo, total canônico ou contrato de API foi alterado.
- Rolagem por eventos de roda do navegador verificou cada linha nas três
  larguras: linha inteira entre cabeçalho e barra inferior, com teste de obstrução
  via `elementFromPoint`. Nenhum conteúdo inacessível: não foi necessário corrigir
  a barra. Capturas de viewport no fim da rolagem mostram a reserva de espaço.
- Larguras preservadas: contêiner de 640px no tablet de 768px e conteúdo de 960px
  em desktop de 1440px.
- Validação: TypeScript, build, 16 E2E visuais e 7 testes de modelo aprovados.
  O E2E de Já pagas compara transações e resumo canônico antes/depois da consulta,
  usando despesas fixas, obrigações variáveis vinculadas, compras cotidianas,
  previsões e faturas com quitação completa/parcial em dados sintéticos locais.

| Largura | Lançamentos | Contas | Fim da rolagem |
| --- | --- | --- | --- |
| 320px | [Tela](refinamento-visual-v2/complemento/lancamentos-320.png) | [Tela](refinamento-visual-v2/complemento/contas-320.png) | [Viewport](refinamento-visual-v2/complemento/contas-fim-rolagem-320.png) |
| 400px | [Tela](refinamento-visual-v2/complemento/lancamentos-400.png) | [Tela](refinamento-visual-v2/complemento/contas-400.png) | [Viewport](refinamento-visual-v2/complemento/contas-fim-rolagem-400.png) |
| 768px | [Tela](refinamento-visual-v2/complemento/lancamentos-768.png) | [Tela](refinamento-visual-v2/complemento/contas-768.png) | [Viewport](refinamento-visual-v2/complemento/contas-fim-rolagem-768.png) |
