# Sentavos

**Sentavos: centavos com s de sergio. cada centavo no seu lugar.**

Meu sistema de controle financeiro pessoal. Estou desenvolvendo porque cansei de
usar planilha e nenhum outro app atende 100% do que eu preciso.

É um app de **uma conta só** — a minha. Não tem cadastro, não tem multi-usuário:
existe um e-mail e uma senha configurados no servidor, e mais ninguém entra.

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

- **API** — FastAPI + SQLModel, Postgres
- **Front** — Vite + React + TypeScript
- **Auth** — própria: Argon2id pra senha, JWT assinado pela própria API

Sem dependência de serviço externo de autenticação. Já foi Supabase Auth, e saiu:
projeto free hiberna após ~1 semana parado, e hibernar derrubava o login junto —
ou seja, voltar de viagem e não conseguir abrir o próprio app. Auth de um usuário
só é pequena o bastante pra morar no projeto.

## Rodando local

```bash
# 1. Gere suas credenciais (pede a senha escondida e imprime o que colar)
uv sync
uv run python -m app.criar_senha

# 2. Backend — http://localhost:8000
cp .env.example .env      # cole as três variáveis + DATABASE_URL
uv run uvicorn app.main:app --reload

# 3. Frontend — http://localhost:5173
cd frontend
npm install
cp .env.example .env
npm run dev
```

Testes: `uv run pytest`

## Deploy

Duas peças: API + banco no **Railway**, front na **Vercel**.

### 1. Gere as credenciais

```bash
uv run python -m app.criar_senha
```

Guarde a saída — são três variáveis do passo seguinte. A senha em si não fica
salva em lugar nenhum; se esquecer, rode de novo e troque as variáveis.

### 2. Railway

New Project → Deploy from GitHub → este repo. O `Dockerfile` e o `railway.json`
são detectados sozinhos.

Depois, **New → Database → Add PostgreSQL** no mesmo projeto.

Variáveis do serviço da API:

| Variável | Valor |
| --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` — referência, não copie a string |
| `SENTAVOS_EMAIL` | seu e-mail |
| `SENTAVOS_SENHA_HASH` | o hash gerado no passo 1 |
| `SENTAVOS_JWT_SECRET` | o segredo gerado no passo 1 |
| `CORS_ORIGINS` | o domínio da Vercel (passo 4) |

`PORT` o Railway injeta sozinho — não defina na mão.

Settings → Networking → **Generate Domain**. Abra a URL: tem que responder
`{"message":"API do Sentavos no ar"}`.

As tabelas são criadas no primeiro boot, pelo `create_all`.

### 3. Vercel

- **Root Directory**: `frontend`
- Build e rewrite de SPA vêm do `frontend/vercel.json` — não precisa configurar.
- Variável: `VITE_API_URL` = o domínio do Railway, **sem barra no final**.

> **Ela é lida na hora de compilar, não em runtime.** Definir depois do build não
> resolve: tem que redeployar. Se faltar, o app mostra uma tela dizendo isso em
> vez de página branca.

O `vercel.json` reescreve toda rota pro `index.html`. Sem isso, abrir
`/orcamento` direto — atalho na tela inicial, link salvo ou um F5 — daria 404,
porque não existe arquivo com esse nome no `dist/`. O bug **não reproduz local**:
o `vite preview` já faz esse fallback sozinho.

### 4. Volte no Railway

Preencha `CORS_ORIGINS` com o domínio que a Vercel gerou. É o passo que se
esquece: sem ele o navegador bloqueia toda chamada e o app parece quebrado sem
nenhum erro no log da API.

### 5. No celular

Abra no Chrome/Safari e use "Adicionar à tela inicial". Abre em tela cheia, com
ícone próprio, sem barra do navegador.

### Primeiro acesso

O banco nasce vazio e **lançamento exige categoria**. Antes de tudo, vá em
Configurações e cadastre suas categorias.

## Segurança

O app é de uma conta só. Mostrar pra alguém não dá acesso a nada.

| Camada | O quê |
| --- | --- |
| **Senha** | Argon2id com salt aleatório. O servidor guarda o hash, nunca a senha. |
| **Token** | JWT HS256 assinado pela API, com `iss`/`aud`/`exp` exigidos. Lista fechada de algoritmos — `alg: none` não passa. |
| **Rotas** | Todas sob `APIRouter(dependencies=[Depends(require_user)])` — rota nova nasce protegida. |
| **Força bruta** | Por IP: **10 respostas 401/403 a cada 5 min**, cota separada da geral (240 req/min). Depois disso nem a senha certa passa. |
| **Tempo constante** | A senha é verificada mesmo com e-mail errado, e a mensagem de erro é a mesma nos dois casos — senão o tempo de resposta diria qual campo acertar. |
| **Corpo** | Requisição acima de 256 KB é recusada com 413 antes de virar JSON. |
| **Docs** | `/docs` e `/openapi.json` desligados em produção. |
| **Cabeçalhos** | `nosniff`, `X-Frame-Options`, CSP e `Cache-Control: no-store` na API; CSP + HSTS + `Permissions-Policy` no front. |
| **Container** | Roda como usuário não-root. |

### Se um aparelho sumir

Defina `SENTAVOS_TOKEN_EPOCH` no Railway com o timestamp atual:

```bash
python -c "import time; print(int(time.time()))"
```

Todo token emitido antes disso para de valer na hora. É o que substitui uma
lista de sessões — que este app não tem de propósito, porque sessão no servidor
seria estado pra manter, sincronizar e perder num redeploy.

### Onde o token fica no navegador

`localStorage`, e não cookie `httpOnly`. O motivo é prático: front na Vercel e
API no Railway são domínios diferentes, cookie entre domínios exige
`SameSite=None`, e o Safari do iPhone bloqueia isso com força — quebraria
exatamente o caso de uso que motivou tudo, que é abrir no celular.

A troca é que um XSS conseguiria ler o token. O que reduz o risco: a CSP não
deixa carregar script de fora nem inline, e o app não renderiza HTML de terceiros
em lugar nenhum.

### Se algo quebrar depois do deploy, olhe a CSP primeiro

- **App abre mas não fala com a API** → `connect-src` no `frontend/vercel.json`.
  Libera `*.up.railway.app`; com **domínio próprio**, adicione-o ali.
- **App abre sem estilo** → `style-src 'self'`, que barra `<style>` injetado em
  runtime. O build atual não tem nenhum e o React aplica `style={{}}` via CSSOM,
  que a CSP não governa — mas se entrar uma biblioteca que injeta CSS, o remédio
  é `style-src 'self' 'unsafe-inline'`.

O console do navegador nomeia exatamente a diretiva que bloqueou.

## Ainda não tem

- **Migrações.** O `create_all` no startup cria tabela que falta, mas nunca altera
  uma que já existe. Adicionar um campo hoje exige mexer no banco à mão. Vai
  precisar de Alembic antes da primeira mudança de schema em produção.
- **Backup automático** do Postgres.
- **Cotação automática** de investimento — saldo é preenchido à mão, mês a mês.
- **Troca de senha pela interface** — hoje é rodar o `criar_senha` e atualizar as
  variáveis no host.
