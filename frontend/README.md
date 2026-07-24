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
  lib/        tipos, cliente da API, hooks de dados (React Query), formatação
  components/ Layout (menu + logo) e Modal
  pages/      Painel, Transações, Categorias
```

## Deploy (Vercel)

- Root do projeto: `frontend`
- Build command: `npm run build` · Output: `dist`
- Variável de ambiente: `VITE_API_URL` apontando pra API em produção.
