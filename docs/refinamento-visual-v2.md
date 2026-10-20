# Refinamento visual V2

Implementado a partir de `origin/main` (`622c783`), na branch `feat/refinamento-visual-v2`.
Revisão feita no aplicativo React existente, com API e PostgreSQL locais e dados
sintéticos. As capturas antes/depois usam o mesmo usuário de teste.

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
