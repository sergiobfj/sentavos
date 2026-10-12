# Fluxo de trabalho: ambientes, CI e o caminho até a main

## Ambientes

| `APP_ENV` | Banco | Onde |
| --- | --- | --- |
| `development` (padrão) | Postgres local (`scripts/postgres_local.py`, porta 54329) | `.env` |
| `test` | SQLite em memória (ou `TEST_DATABASE_URL` local) | `pytest`, CI |
| `production` | Neon | Render (variável do serviço) |

`app/ambiente.py` decide e trava: fora de `production`, banco remoto é
recusado. Uma ferramenta **local** só conecta na produção com as duas coisas
ao mesmo tempo — o arquivo de produção e a permissão na linha de comando:

```bash
ALLOW_PRODUCTION_DATABASE=true uv run --env-file .env.production.local python -m scripts.backup --usuario voce@exemplo.com
```

`.env.production.local` fica só na máquina (o `.gitignore` cobre `.env.*`). A
URL de produção nunca vai pro `.env` nem pra arquivo versionado. Scripts que
escrevem são dry-run por padrão (`--apply` pra gravar) e fazem backup antes.

## Do código à produção

1. Branch `feat/...` a partir da `main`.
2. Push da branch: o CI roda (`.github/workflows/ci.yml`):
   - **backend**: `uv sync --frozen` + `pytest`;
   - **migrações**: Postgres 16 de verdade — vazio → head → desce até 0007 →
     head; fixture fictícia em 0007 → head, com os mesmos números que a fixture
     carregada direto em head;
   - **frontend**: `npm ci` + `tsc` + build.
3. Pull request pra `main`. Merge só com o CI verde.
4. O merge publica: Render (API) e Vercel (front) fazem deploy da `main`.
   Mudança de contrato vai em dois PRs: primeiro o backend compatível com o
   front antigo (campos novos opcionais), depois o front.

Antes de um release que mexe em dado: ensaio local numa cópia dos backups
(`scripts/regressao.py carregar / despejar / comparar --corte AAAA-MM`). Dado
real nunca vai pro CI.

Branches `feat/*` não geram preview na Vercel (`git.deploymentEnabled` em
`frontend/vercel.json`), e a API de produção só aceita CORS de
`https://sentavos.vercel.app` — um preview, se existisse, não conseguiria
chamar a produção do navegador.

## Proteger a main (manual, no GitHub)

*Settings → Branches → Add branch ruleset* (ou *Branch protection rule*) para `main`:

1. **Require a pull request before merging** — sem aprovação obrigatória
   (projeto de uma pessoa), mas tudo passa por PR.
2. **Require status checks to pass** → marque `backend (pytest)`,
   `migrações (Postgres)` e `frontend (tsc + build)` (aparecem depois da
   primeira execução do CI) e **Require branches to be up to date**.
3. **Block force pushes** e **Restrict deletions**.
4. **Do not allow bypassing the above settings** (vale pra você também).

Branches de feature continuam livres.

## Recomendações de deploy (não aplicadas)

- **Render** → serviço → *Settings → Build & Deploy → Auto-Deploy*: trocar
  para **"After CI Checks Pass"**. Com a main protegida já é redundante, mas
  fecha a porta de um push que escape da regra.
- **Render** → *Environment*: definir `APP_ENV=production` explicitamente (o
  código já trata o Render como produção quando falta, mas explícito é melhor).
- Deploy hooks acionados pelo CI só valem a pena se um dia houver etapa entre
  o merge e o deploy (ex.: migração separada do startup). Hoje, não.
