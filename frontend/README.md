# PitchPulse frontend

React 18 + Vite + Tailwind, TypeScript strict. It shows one synthetic match
from the Matchmind engine: studio, broadcast overlay, fan vs analyst split,
player focus and "My match" (favourite club and single-metric mode), in
English, Spanish and Arabic (right-to-left).

## Run

```bash
npm ci
npm run dev                                    # http://localhost:3000
VITE_API_URL=http://127.0.0.1:8000 npm run dev # against a local backend
```

The app talks to the backend over `/ws/match` and the REST routes in
`docs/API-CONTRACT.md` (TypeScript twin: `src/api/contract.ts`). With no
`VITE_API_URL` it uses the page's own origin, which is how the backend serves
the built app from `static/`.

If the match server cannot be reached within a few seconds, the app says so
and plays an **offline demo**: a recording of the engine's demo match
(`public/demo/demo-match.json`) replayed in the browser with the same
messages. Rebuild it with `python frontend/scripts/build_demo_fixture.py` from
the repo root (needs the backend package installed).

URL options: `?demo=1` forces the offline demo, `?live=1` never falls back,
`?t=2056&p=1&pause=1` opens at a match moment (clock seconds and half),
`#studio | #overlay | #split | #follow | #fan` picks the screen.

## Checks

```bash
npm run typecheck && npm test && npm run build
```

All visible text goes through `src/i18n`; every key must exist in en, es and
ar (a test enforces it).
