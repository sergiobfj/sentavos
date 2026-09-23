# Sentavos

**Sentavos: centavos com s de sergio. cada centavo no seu lugar.**

Meu sistema de controle financeiro pessoal. Estou desenvolvendo porque cansei de
usar planilha e nenhum outro app atende 100% do que eu preciso.

É um app de **uma conta só** — a minha. Não tem cadastro, não tem multi-usuário:
existe um e-mail e uma senha configurados no servidor, e mais ninguém entra.

## As cinco abas

| Aba | O que responde |
| --- | --- |
| **Visão geral** | Como foi o mês: entrou, gastou, sobrou na conta. |
| **Orçamento** | Orçado × previsto × pago por categoria, os lançamentos do mês e as faturas dos cartões. |
| **Investimento** | Quanto tenho aplicado e como está dividido. Visão cruzada de Patrimônio — não guarda dado próprio. |
| **Patrimônio** | Quanto cada coisa vale hoje, incluindo dívida (que entra subtraindo). |
| **Configurações** | Cartões, CDI e categorias. |

Transação é **fluxo** (o que se moveu no mês); ativo é **estoque** (quanto vale
num ponto do tempo). Por isso patrimônio não sai da soma das transações — precisa
de saldo lançado à mão, mês a mês.

## Gasto não é saída de caixa

O app separa duas coisas que ele tratava como uma só. É a distinção que faz
cartão de crédito funcionar:

| | O que é | Onde aparece |
| --- | --- | --- |
| **Gasto** | o que você consumiu no mês | "Gastou", metas, "para onde foi" |
| **Saída de caixa** | o que saiu da conta no mês | "Carteira" |

Compra no cartão é gasto **na hora** e saída de caixa **só quando a fatura é
paga**. Pagar a fatura é saída de caixa e **não** é gasto novo — o gasto já foi
contado quando cada compra foi lançada. Contar de novo somaria o mesmo dinheiro
duas vezes.

### Cartões

Um cartão tem nome, dia de fechamento e dia de vencimento. Nada mais: sem
limite, sem bandeira, sem cor. A compra feita **até** o dia do fechamento entra
na fatura que fecha nesse dia; a partir do dia seguinte, na próxima.

O app descobre a fatura sozinho — você nunca escolhe uma na mão.

Fatura vencida com saldo aparece como **atrasada**. Juros, multa, rotativo e
IOF não são calculados de propósito: são regra de banco, mudam por contrato e
errar neles é pior do que não ter. Cobrança dessas entra como um lançamento
normal, com o valor que o banco cobrou de fato.

### Parcelamento

Uma compra de R$ 900 em 3× vira três parcelas de R$ 300, uma por mês a partir do
mês da compra, cada uma na fatura do seu ciclo. As três continuam ligadas à
compra: abrir qualquer uma mostra o total, "2 de 3" e o cartão.

Quando o valor não divide certo, o resto vai na **primeira** parcela — R$ 100 em
3× são 33,34 + 33,33 + 33,33. A soma é sempre exata.

Parcela não se edita nem se apaga sozinha (a compra inteira, sim), e depois que
uma fatura dela é paga, valor, parcelas, cartão e data travam: mexer reescreveria
uma fatura que já foi cobrada.

### Competência × cobrança

Compra em 28/09 num cartão que fecha 25 é gasto de **setembro** — foi quando
aconteceu — e é cobrada na fatura que vence em **novembro**. São quatro datas
diferentes e o app guarda as quatro: data da compra, competência do gasto, fatura
que cobra e data do pagamento.

### Lançamentos anteriores ao cartão

Quem já usava o app tem lançamentos sem forma de pagamento definida. A migração
**não** marca nenhum deles como "à vista": parte foi no cartão, e chutar seria
inventar dado financeiro.

Até serem revisados eles contam como saída de caixa — que é como já eram
contados, então nenhum número de nenhum mês passado muda. O app avisa quantos
estão assim e leva pra tela de revisão, onde dá pra responder em lote.

Se você registrava a fatura como uma despesa numa categoria tipo "Fatura do
cartão", a tela da fatura tem **"já lancei este pagamento como despesa"**: o
lançamento antigo vira o pagamento daquela fatura e deixa de contar como gasto,
em vez de o mesmo dinheiro ser contado duas vezes. É uma operação explícita,
escolhida item a item — o app nunca faz isso sozinho por causa do nome da
categoria.

## Stack

- **API** — FastAPI + SQLModel, Postgres (Neon)
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
uv run python -m app.criar_usuario

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

Três peças, todas no plano gratuito: banco no **Neon**, API no **Render**, front
na **Vercel**.

> **Por que o banco não fica no Render.** O Postgres free dele é apagado depois de
> 30 dias. Num app de finanças isso é perder o histórico inteiro sem aviso. O Neon
> é free e não expira — ele suspende o compute quando fica ocioso, mas acorda em
> milissegundos e de forma transparente.

### 1. Gere as credenciais

```bash
uv run python -m app.criar_usuario
```

Guarde a saída: são três das variáveis do passo 3. A senha em si não fica salva
em lugar nenhum; se esquecer, rode de novo e troque as variáveis.

### 2. Banco no Neon

**neon.tech** → crie um projeto → copie a **connection string** (a "pooled", que
tem `-pooler` no host). É a sua `DATABASE_URL`.

Ela já vem com `?sslmode=require`. Mantenha.

### 3. API no Render

**render.com** → **New** → **Blueprint** → aponte pro repo. Ele lê o
`render.yaml` e monta o serviço sozinho; só vai pedir as cinco variáveis:

| Variável | Valor |
| --- | --- |
| `DATABASE_URL` | a connection string do Neon |
| `SENTAVOS_EMAIL` | seu e-mail |
| `SENTAVOS_SENHA_HASH` | o hash do passo 1 (começa com `$argon2id$`) |
| `SENTAVOS_JWT_SECRET` | o segredo do passo 1 |
| `CORS_ORIGINS` | `http://localhost:5173` por enquanto — trocado no passo 5 |

`PORT` o Render injeta sozinho — não defina na mão.

O primeiro build demora alguns minutos (é Docker). Quando terminar, abra a URL
`https://sentavos-api.onrender.com`. Tem que responder:

```json
{"message":"API do Sentavos no ar"}
```

As tabelas são criadas nesse primeiro boot, pelas migrações do Alembic — elas
rodam sozinhas no startup. Veja a seção **Migrações**.

Teste o login antes de seguir:

```bash
curl -X POST https://SEU-APP.onrender.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"seu@email.com","senha":"sua-senha"}'
```

Tem que voltar um `access_token`. Se voltar **401**, o hash foi colado cortado
(ele tem `$` no meio). Se voltar **500**, falta alguma das três variáveis.

### 4. Front na Vercel

- **Root Directory**: `frontend`
- Build e rewrite de SPA vêm do `frontend/vercel.json` — não precisa configurar.
- Variável: `VITE_API_URL` = a URL do Render, **sem barra no final**.

> **Ela é lida na hora de compilar, não em runtime.** Definir depois do build não
> resolve: tem que redeployar. Se faltar, o app mostra uma tela dizendo isso em
> vez de página branca.

O `vercel.json` reescreve toda rota pro `index.html`. Sem isso, abrir
`/orcamento` direto — atalho na tela inicial, link salvo ou um F5 — daria 404,
porque não existe arquivo com esse nome no `dist/`. O bug **não reproduz local**:
o `vite preview` já faz esse fallback sozinho.

### 5. Volte no Render

Troque `CORS_ORIGINS` pelo domínio que a Vercel gerou. É o passo que se esquece:
sem ele o navegador bloqueia toda chamada e o app parece quebrado sem nenhum erro
no log da API.

### 6. No celular

Abra no Chrome/Safari e use "Adicionar à tela inicial". Abre em tela cheia, com
ícone próprio, sem barra do navegador.

### Primeiro acesso

O banco nasce vazio e **lançamento exige categoria**. Antes de tudo, vá em
Configurações e cadastre suas categorias.

### O cold start do Render free

O serviço hiberna após ~15 minutos parado, e a primeira chamada depois disso
demora **~50 segundos** enquanto o container sobe. Na prática: você abre o app,
digita a senha, e ela parece travada por um tempo desconfortável.

Não é bug e não tem conserto no plano gratuito. As saídas, quando incomodar:

- **Render Starter (US$ 7/mês)** — acaba com a hibernação.
- **Um pinger externo** (UptimeRobot e afins) batendo no `/` a cada 10 minutos
  mantém acordado. Funciona, mas consome as 750 horas/mês do free tier — que dão
  exatamente um serviço rodando 24/7, sem folga pra um segundo.

O banco no Neon não tem esse problema: ele acorda sozinho em milissegundos.

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

Defina `SENTAVOS_TOKEN_EPOCH` no Render com o timestamp atual:

```bash
python -c "import time; print(int(time.time()))"
```

Todo token emitido antes disso para de valer na hora. É o que substitui uma
lista de sessões — que este app não tem de propósito, porque sessão no servidor
seria estado pra manter, sincronizar e perder num redeploy.

### Onde o token fica no navegador

`localStorage`, e não cookie `httpOnly`. O motivo é prático: front na Vercel e
API no Render são domínios diferentes, cookie entre domínios exige
`SameSite=None`, e o Safari do iPhone bloqueia isso com força — quebraria
exatamente o caso de uso que motivou tudo, que é abrir no celular.

A troca é que um XSS conseguiria ler o token. O que reduz o risco: a CSP não
deixa carregar script de fora nem inline, e o app não renderiza HTML de terceiros
em lugar nenhum.

### Se algo quebrar depois do deploy, olhe a CSP primeiro

- **App abre mas não fala com a API** → `connect-src` no `frontend/vercel.json`.
  Libera `*.onrender.com`; com **domínio próprio**, adicione-o ali.
- **App abre sem estilo** → `style-src 'self'`, que barra `<style>` injetado em
  runtime. O build atual não tem nenhum e o React aplica `style={{}}` via CSSOM,
  que a CSP não governa — mas se entrar uma biblioteca que injeta CSS, o remédio
  é `style-src 'self' 'unsafe-inline'`.

O console do navegador nomeia exatamente a diretiva que bloqueou.

## Migrações

**Alembic**, rodando no startup (`create_db_and_tables` chama `alembic upgrade
head`). Não use `create_all` pra mudar schema: ele cria tabela que falta e nunca
altera uma que já existe.

| | O que fez |
| --- | --- |
| `0001_multiusuario` | `user_id` em cinco tabelas, com as linhas existentes adotadas |
| `0002_caixinhas` | categorias arquiváveis |
| `0003_rendimento` | `cdi_percent` no ativo e `cdi_annual` no usuário |
| `0004_cartao` | cartões, compras, faturas, pagamentos e a forma de pagamento |

Toda migração é **idempotente por coluna**: ela checa antes de adicionar. Num
banco vazio a `0001` monta as tabelas com `create_all`, que usa o modelo de hoje
— ou seja, já com as colunas das migrações seguintes. Sem a checagem,
`alembic upgrade head` num ambiente novo morre com "duplicate column", e como a
API roda o upgrade no startup, **o app não sobe**.

Antes de rodar contra dado real, ensaie numa cópia: copie a conta pro SQLite,
`alembic stamp head` nela e rode. `scripts/backup.py` copia a conta inteira pra
um JSON em `backups/` — use antes de qualquer script que escreva.

> **Enum vem do modelo, nunca de strings escritas na migração.** O SQLAlchemy
> grava o NOME do membro (`CREDIT`), não o valor (`credit`). `sa.Enum("credit",
> …)` criaria no Postgres um tipo que recusa exatamente o que o ORM manda — e a
> suíte não pegaria, porque os testes montam o banco com `create_all` e nunca
> executam a migração. Erro que só aparece em produção.

## Ainda não tem

- **Backup automático** do Postgres.
- **Cotação automática** de investimento — saldo é preenchido à mão, mês a mês.
- **Troca de senha pela interface** — hoje é rodar o `criar_usuario` e atualizar as
  variáveis no host.
