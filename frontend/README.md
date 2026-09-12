# Frontend

React + Vite dashboard for the Highway Risk Intelligence prototype. Phase 1
scope is a single page that checks the backend `/health` endpoint.

## Setup

```bash
npm install
npm run dev
```

Runs at `http://localhost:5173` by default and expects the backend at
`http://127.0.0.1:8000` (override with a `VITE_API_BASE_URL` env var, see
`.env.example`).

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build to `dist/`
- `npm run preview` — preview the production build locally
