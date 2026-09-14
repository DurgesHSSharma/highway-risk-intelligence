# Frontend

React + Vite dashboard for the Highway Risk Intelligence prototype — see
[../docs/FRONTEND_DASHBOARD.md](../docs/FRONTEND_DASHBOARD.md) for the full
architecture, routes, design system, and browser-verification results.

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
- `npm run test` — run the frontend test suite once (vitest)
- `npm run test:watch` — run the frontend test suite in watch mode
