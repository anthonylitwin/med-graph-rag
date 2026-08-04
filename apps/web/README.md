# Vue frontend (Vite + TypeScript)

This directory contains the active MedGraphRAG web UI built with Vue 3, Vue
Router, TypeScript, and Vite.

## Prerequisites

- Node.js 20+
- npm 10+

## Run locally

```bash
npm install
npm run dev
```

The dev server starts on `http://localhost:5173` by default.

## Build for production

```bash
npm run build
npm run preview
```

The app expects `VITE_API_BASE_URL` to point at the FastAPI service. If unset,
it defaults to `http://localhost:8000`.
