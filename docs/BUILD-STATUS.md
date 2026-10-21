# Build status

Last updated: 20 Oct 2026. Preview URL: not deployed yet.

| Area | Status | Evidence |
|---|---|---|
| Simulator and event schema | Done | `cd backend && pytest` (24 tests); dataset regenerates byte for byte |
| Fictional clubs and players | Done | `backend/src/matchmind/simulator/teams.py` |
| Stats engine: metrics and models | Started | Chance quality calibration checked by hand; tests to do |
| Stats engine: better option, rolling state | To do | See `docs/NEXT-STEPS.md` section 2 |
| AI studio crew | To do | Section 3 |
| Match session and API | To do | Section 4. The old `backend/api` was removed in this branch, so the frontend has no backend until this lands |
| Frontend updates | To do | Section 5. Still shows old team names and the removed auto-eventing badge |
| Deployment and CI | To do | Section 6. Bicep still outputs keys: do not deploy it as is |
| README and plan | To do | Section 7. README still describes the old build |

## Known issues carried over from the first build

- Real player names and look-alike club names (removed from the backend in
  this branch; the frontend still has some).
- "Auto-eventing" vision model presented as live; no such model exists.
- Bicep template outputs service keys.
- API allowed every origin with credentials.
