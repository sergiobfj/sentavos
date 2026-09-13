# Sentavos

**Sentavos: centavos com s de sergio. cada centavo no seu lugar.**

Meu sistema de controle financeiro pessoal. Estou desenvolvendo porque cansei de
usar planilha e nenhum outro app atende 100% do que eu preciso.

É um app de **uma conta só** — a minha. Não tem cadastro, não tem multi-usuário:
a API checa o `sub` do token contra um UUID fixo e recusa qualquer outro.

## As cinco abas

| Aba | O que responde |
| --- | --- |
| **Visão geral** | Como foi o mês: entrou, saiu, sobrou. |
| **Orçamento** | Orçado × previsto × pago por categoria, e os lançamentos do mês. |
| **Investimento** | Quanto tenho aplicado e como está dividido. Visão cruzada de Patrimônio — não guarda dado próprio. |
| **Patrimônio** | Quanto cada coisa vale hoje, incluindo dívida (que entra subtraindo). |
| **Configurações** | Categorias. |

Transação é **fluxo** (o que se moveu no mês); ativo é **estoque** (quanto vale
num ponto do tempo). Por isso patrimônio não sai da soma das transações — precisa
de saldo lançado à mão, mês a mês.

## Stack

- **API** — FastAPI + SQLModel, Postgres (Supabase)
- **Front** — Vite + React + TypeScript
- **Auth** — Supabase Auth; a API valida o JWT (HS256 legado ou ES256/RS256 via JWKS)

## Rodando local

```bash
# Backend — http://localhost:8000
cp .env.example .env      # preencha DATABASE_URL, SUPABASE_URL, SENTAVOS_ALLOWED_USER_ID
uv sync
uv run uvicorn app.main:app --reload

# Frontend — http://localhost:5173
cd frontend
npm install
cp .env.example .env
npm run dev
```

Testes: `uv run pytest`

## Deploy

Três peças: banco no **Supabase**, API no **Railway**, front na **Vercel**.

### 1. API no Railway

O `Dockerfile` e o `railway.json` já estão no repo — o Railway detecta os dois
sozinho. Aponte o serviço pra raiz deste repositório e defina as variáveis:

| Variável | Valor |
| --- | --- |
| `DATABASE_URL` | Connection string do Supabase, **porta 6543** (o pooler) |
| `SUPABASE_URL` | `https://seu-projeto.supabase.co` |
| `SENTAVOS_ALLOWED_USER_ID` | Seu UUID em Authentication > Users |
| `SUPABASE_JWT_SECRET` | Só se o projeto ainda usa HS256; senão deixe vazio |
| `CORS_ORIGINS` | O domínio da Vercel, ex. `https://sentavos.vercel.app` |

`PORT` o Railway injeta sozinho — não defina na mão.

> **O `CORS_ORIGINS` é o passo que se esquece.** O padrão no código só cobre
> localhost. Sem ele apontando pro domínio de produção, o navegador bloqueia toda
> chamada e o app parece quebrado sem nenhum erro no log da API.

Como é ovo e galinha (a API precisa do domínio do front, o front precisa da URL
da API), suba a API primeiro, faça o deploy do front, e só então volte e preencha
o `CORS_ORIGINS` com o domínio que a Vercel gerou.

### 2. Front na Vercel

- **Root Directory**: `frontend`
- Build e rewrite de SPA vêm do `frontend/vercel.json` — não precisa configurar.

Variáveis: `VITE_API_URL` (o domínio do Railway), `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`.

> **Estas três são lidas na hora de compilar, não em runtime.** Definir depois do
> build não resolve: tem que redeployar. Se faltarem, o app mostra uma tela
> dizendo exatamente isso em vez de página branca.

O `vercel.json` reescreve toda rota pro `index.html`. Sem isso, abrir
`/orcamento` direto — atalho na tela inicial, link salvo ou um F5 — daria 404,
porque não existe arquivo com esse nome no `dist/`. A Vercel só aplica o rewrite
depois de não achar arquivo estático, então os assets continuam normais.

### 3. No celular

O app é instalável: abra no Chrome/Safari e use "Adicionar à tela inicial". Abre
em tela cheia, com ícone próprio, sem barra do navegador.

### Primeiro acesso

O banco nasce vazio e **lançamento exige categoria**. Antes de tudo, vá em
Configurações e cadastre suas categorias — senão a aba de Orçamento fica sem
nenhuma linha pra preencher.

## Ainda não tem

- **Migrações.** O `create_all` no startup cria tabela que falta, mas nunca altera
  uma que já existe. Adicionar um campo hoje exige mexer no banco à mão. Vai
  precisar de Alembic antes da primeira mudança de schema em produção.
- **Backup automático** do Postgres.
- **Cotação automática** de investimento — saldo é preenchido à mão, mês a mês.
