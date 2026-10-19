# Sentavos — Frontend

Interface web do Sentavos. **Vite + React + TypeScript**, consumindo a API FastAPI.

## Rodando localmente

Pré-requisito: o backend precisa estar no ar (por padrão em `http://localhost:8000`).

```bash
cd frontend
npm install
cp .env.example .env    # ajuste VITE_API_URL se necessário
npm run dev
```

Abre em `http://localhost:5173`.

## Scripts

- `npm run dev` — servidor de desenvolvimento (hot reload)
- `npm run build` — build de produção em `dist/`
- `npm run preview` — serve o build localmente
- `npm run lint` — checagem de tipos (tsc)

## Estrutura

```
src/
  lib/        tipos, cliente da API, sessão/auth, hooks de dados, formatação
  components/ Layout (menu + logo), Modal, formulários
  pages/      Visão geral, Orçamento, Investimento, Patrimônio, Configurações, Login
```

## Deploy (Vercel)

- Root Directory: `frontend`
- Build e rewrite de SPA vêm do `vercel.json` — não precisa configurar na mão.
- Variável: `VITE_API_URL` apontando pra API em produção, sem barra no final.

Veja o README da raiz pro passo a passo completo.

## Sentavos Essencial — protótipo local

Com o Vite em execução, abra `/essencial.html#/`. Esta entrada independente não
precisa do backend: usa somente dados fictícios e alterações em memória,
restauradas ao recarregar. A data demonstrativa é 18/10/2026.

- `npm run build:essencial`: compila a demonstração em `dist-essencial/`.
- `npm run test:essencial`: executa 23 verificações de modelo, tarefas e layout
  com Playwright (Edge instalado no Windows), incluindo 320, 360, 400, 768 e
  1440px. Capturas ficam em `test-results-essencial/` e o relatório HTML em
  `playwright-report-essencial/`.
- O build normal continua gerando apenas a aplicação atual em `dist/`.

Auditoria, proposta de navegação, limites do protótipo e plano de integração:
[`docs/sentavos-essencial.md`](../docs/sentavos-essencial.md).
