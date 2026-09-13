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

## Segurança

O app é de **uma conta só**. Mostrar pra alguém não dá acesso a nada: mesmo que a
pessoa crie conta no projeto Supabase e faça login, a API compara o `sub` do
token com `SENTAVOS_ALLOWED_USER_ID` e responde 403.

O que protege, em camadas:

| Camada | O quê |
| --- | --- |
| **Token** | JWT do Supabase, assinatura verificada (ES256 via JWKS, ou HS256 legado). Lista fechada de algoritmos — `alg: none` não passa. |
| **Emissor** | O `iss` tem que ser o *seu* projeto. Token válido de outro projeto Supabase não serve. |
| **Dono** | O `sub` tem que bater com `SENTAVOS_ALLOWED_USER_ID`. Sem essa variável a API recusa tudo (falha fechada). |
| **Rotas** | Todas sob `APIRouter(dependencies=[Depends(require_user)])` — rota nova nasce protegida. |
| **Cota** | Por IP: 240 req/min no geral e **10 respostas 401/403 a cada 5 min**, que é o que inviabiliza tentar token até acertar. |
| **Corpo** | Requisição acima de 256 KB é recusada com 413 antes de virar JSON. |
| **Docs** | `/docs` e `/openapi.json` desligados em produção. |
| **Cabeçalhos** | `nosniff`, `X-Frame-Options`, CSP e `Cache-Control: no-store` na API; CSP + HSTS + `Permissions-Policy` no front. |

### O passo que não é código: `sql/001_fechar_acesso_direto.sql`

**Rode este arquivo no SQL Editor do Supabase antes de considerar o app seguro.**

O Supabase publica o schema `public` como API REST automática. As tabelas aqui
foram criadas pelo `create_all`, não pelo painel — então nasceram **sem RLS**, e
o GRANT padrão do Supabase dá acesso ao papel `anon`. Como a anon key está no
bundle do front (é pública por design), isso significa que

```
curl 'https://<projeto>.supabase.co/rest/v1/transactions?select=*' -H "apikey: <anon key>"
```

devolveria seus lançamentos **sem passar pela API**, contornando token, `iss` e
allowlist de uma vez. O SQL liga RLS sem nenhuma policy ("ninguém pode nada") e
revoga os GRANTs, inclusive os padrão — pra a próxima tabela que o `create_all`
criar não nascer exposta de novo. A API não é afetada: ela conecta como dono da
tabela, e dono não é submetido a RLS.

Confira rodando aquele `curl` antes e depois: tem que sair de "devolve dado" pra
"permission denied".

### No painel do Supabase

- **Authentication > Providers > Email**: desligue **"Enable signup"**. Sua conta
  já existe; deixar aberto só permite que estranhos criem conta no seu projeto
  (não acessam nada, mas enchem sua base e consomem cota de e-mail).
- **Authentication > Rate limits**: o Supabase tem os limites dele pra tentativa
  de login. Os limites da nossa API valem pras rotas de dados; o login em si
  acontece no Supabase, então esse ajuste é lá.
- **Authentication > Policies**: ative **leaked password protection** se estiver
  disponível no seu plano.

### Se algo quebrar depois do deploy, olhe a CSP primeiro

A CSP do `frontend/vercel.json` é apertada. Dois sintomas e a correção:

- **App abre mas não fala com a API** → `connect-src`. Ele libera
  `*.supabase.co` e `*.up.railway.app`. Se você puser **domínio próprio** na
  API, adicione-o ali.
- **App abre sem estilo** → `style-src 'self'`, que barra `<style>` injetado em
  runtime. O build atual não tem nenhum (conferido) e o React aplica
  `style={{}}` via CSSOM, que a CSP não governa — mas se um dia entrar uma
  biblioteca que injeta CSS, o remédio é `style-src 'self' 'unsafe-inline'`.

O console do navegador nomeia exatamente a diretiva que bloqueou.

## Ainda não tem

- **Migrações.** O `create_all` no startup cria tabela que falta, mas nunca altera
  uma que já existe. Adicionar um campo hoje exige mexer no banco à mão. Vai
  precisar de Alembic antes da primeira mudança de schema em produção.
- **Backup automático** do Postgres.
- **Cotação automática** de investimento — saldo é preenchido à mão, mês a mês.
