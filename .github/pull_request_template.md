## What changed

## Why

## Checks run
- [ ] `make backend` (ruff, format, pytest)
- [ ] `cd frontend && npm run typecheck && npm test && npm run build`
- [ ] Licence check passes
- [ ] Checked at phone and desktop width (UI changes)

## Rules
- [ ] Synthetic data only: no real clubs, players or brands
- [ ] Every number on screen comes from the stats engine
- [ ] Paid Azure services stay off by default, with a working local fallback
- [ ] Independent security review: no open critical or high finding

## Handoff notes
