# Vue frontend (Vite + TypeScript)

This directory contains the active MedGraphRAG web UI built with Vue 3, Vue
Router, TypeScript, and Vite.

## Prerequisites

- Node.js 20+
- npm 10+

## Run locally

From this directory:

```bash
npm install
npm run dev
```

The dev server starts on `http://localhost:5173` by default.

On Windows PowerShell, if `npm` is blocked by execution policy, use `npm.cmd`:

```powershell
npm.cmd install
npm.cmd run dev
```

## Run with Docker Compose

From the repo root:

```bash
docker compose up web
```

The Compose dev service runs `npm install` before starting Vite so the
container's mounted `node_modules` volume stays in sync with `package.json`.
If an old dependency volume still causes import-resolution errors, reset it
once with:

```bash
docker compose down -v
docker compose up --build web
```

## Build for production

```bash
npm run build
npm run preview
```

The app expects `VITE_API_BASE_URL` to point at the FastAPI service. If unset,
it defaults to `http://localhost:8000`.
