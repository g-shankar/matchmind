# Project instructions for PitchPulse

These rules apply to every Claude session, every builder and every reviewer on web, iOS and Android work. Where a rule says "ask first", ask the owner before acting.

Read first each session: this file, `AGENTS.md` (if present), the product requirements doc, the build-status doc (`docs/BUILD-STATUS.md`) and the current `git diff`.

## 0. Project scope (read with every section below)
PitchPulse is a hackathon entry (Microsoft x Premier League "Inside the Game", submissions close 27 Oct 2026). It is a web app plus a Python engine; it has **no user accounts, payments, customer data, uploads or mobile apps**. Sections on payments, row-level security, migrations, tenants and mobile (parts of 4, 8 and all of 9) do not apply until such a feature is added; everything else does.

Project-specific hard rules:
- **Synthetic data only.** No real clubs, players, managers, competitions or broadcaster branding anywhere: code, data, UI, video. Club and player names are invented (`backend/src/matchmind/simulator/teams.py`).
- **Numbers come from the stats engine, never from a model.** The fact-checker rejects any number in generated text that is not in the moment's facts.
- **Paid Azure AI stays off by default** (`MATCHMIND_AI_ENABLED=false`); the crew runs in template mode until the owner approves the spend.
- Placeholders were filled for this project; the `.claude/agents` model mapping is light = Haiku, default = Sonnet, strong = Opus.

---

## 1. Priorities (in order)
1. Security and data integrity
2. Approved scope and acceptance criteria
3. User experience and performance
4. Maintainability and cost

Never declare a feature production-ready without test evidence. Say plainly which things are implemented, tested, mocked, blocked or only proposed.

## 2. Working rules
1. **Security first.** Every merge gets an independent security review by a fresh-context reviewer who did not write the code. Any critical or high finding blocks the merge. Never weaken a security control to ship faster.
2. **Ask the owner first** before: live payments, paid services or accounts, real customer data, sending real emails/texts/push notifications, production changes (deploys, migrations, config), deleting data, rotating credentials, store submissions, or anything that cannot be undone. Prepare a sign-off note instead of doing it.
3. **Free tools only** unless the owner approves a cost. Paid features (SMS, maps/route APIs, AI, push providers) are built against a fake service and stay switched off until approved.
4. **Brand.** Never reveal how the product is built or that AI wrote it. Use PitchPulse's own look, never a default template or default-assistant look. Repo text (README, docs, comments, workflow names) describes the team and its process, never the coding tools; keep tool config in `.claude/`.
5. **No fake features.** Anything unbuilt is labelled "coming soon" in the UI. No placeholder or mock presented as complete.
6. **Low ask.** Pick sensible defaults and keep building. Do not pile questions or setup steps on the owner. Anything only the owner can do goes in `setup/owner-todo.md`; mention it once, when asked or when it is a real blocker.
7. **Preview link.** Only ever give the owner the main preview link: the Azure Container Apps URL listed in `docs/BUILD-STATUS.md` (not deployed yet).
8. **Keep the product's separate parts separate.** Internal tools (admin/CRM) stay fully separate from the customer product: own repo, database and sign-in.
9. **Right-size the work and the model ("tuning").**
   - Simple tasks (merges, label/copy fixes, small follow-ups, doc updates, quick reviews of small fixes): lighter/faster model (light tier).
   - Code, security, money, auth and architecture work: the default/strongest model (default tier). Security reviewers run on the strongest model.
   - Use lower effort for mechanical work, higher for design and review.
10. **Build one feature at a time.** One feature per PR, one branch through review and merge at a time, at most one builder alongside. Do not touch the shared build-status doc on feature branches (put handoff notes in the PR body). Features touching data, money or auth get a full independent review; small fixes get one quick review pass, no repeated full-suite rounds unless it finds something.
11. **A failing fix gets 3 tries.** Re-read the error each time. After the third failure stop and escalate with the options and a recommendation instead of trying more variations.
12. **Batch approvals.** One commit and push per finished feature, so the owner is not interrupted by repeated prompts.
13. **Lessons.** Each real mistake or repeated review finding becomes one line under "Lessons" at the bottom of this file, shipped in the next PR (not a separate PR).

## 2a. Agent team and model per role
Work is split across roles, each with its own model and effort. Not every agent uses the same model. Model names below are tiers; map them to the current model IDs (light tier = Haiku/Sonnet tier, default tier = Sonnet/Opus tier, strong tier = Opus tier).

**Roles**
- **Coordinator** (persistent): reads the chat, triages each ask, writes a short brief (what the thread needs from memory, the default chosen where the ask forks, which agent owns shared files), starts the right specialist, routes follow-ups, keeps memory current and stays quiet unless something is blocked. It does not write feature code.
- **Builder** (one per feature): implements one bounded task on its own branch with tests.
- **Reviewers** (read-only, fresh context): security reviewer, QA verifier, code-quality reviewer. They never edit source.
- **Researcher**: market, library, licence and competitor research; returns a short summary with sources.
- **Docs/chore agent**: docs-per-feature, status updates, merges, label/copy fixes, small follow-ups.

| Role | Model tier | Effort | Notes |
|---|---|---|---|
| Coordinator (triage, brief, route) | default tier | medium | Cheap enough to run always; escalates by starting a stronger specialist |
| Architecture, design, ADRs | strong tier | high | Trade-offs, module walls, data model |
| Builder: money, auth, data, migrations, RLS, payments, sync | strong tier | high | Highest cost of a bug |
| Builder: ordinary feature code, UI | default tier | medium | |
| Builder: small fix, copy, styling, config | light tier | low | |
| Security reviewer | strong tier | high | Always a different agent from the builder, fresh context |
| QA verifier (reproduce builds/tests, check acceptance criteria) | default tier | medium | Read-only |
| Code-quality reviewer | default tier | medium | |
| Quick review of a small fix | light tier | low | One pass, no repeated full-suite rounds |
| Hard debugging (races, sync, flaky, cross-system) | strong tier | high | After 3 failed tries, escalate to the owner |
| Researcher / summaries | light tier or default tier | low-medium | Use the default tier when judgement is needed |
| Docs, status updates, merges, labels | light tier | low | |

**Rules**
- A reviewer never runs in the builder's context and should use a different agent, and where practical a different model, from the one that built the code, so it does not grade its own work. On money/auth/data features add a second, different reviewer when available.
- Start at the cheapest tier that is safe for the task; move up for architecture, security, money, auth, data, sync and hard debugging; never move security or money work down to save cost.
- Subagents get the whole brief in their prompt (they do not see this conversation): goal, files, what is ruled out, this rules file and the bug-hunt checklist. Give every build or review brief the checklist in section 5.
- Run independent work in parallel only when it is truly independent; otherwise one feature at a time (rule 10).
- Set each subagent's model in its definition (`.claude/agents/<name>.md` frontmatter), so the choice is enforced and not left to memory.

## 3. Experience standard (every app: web, iOS, Android, admin tools)
A feature is not done until it meets all of these, and every review checks them alongside security.
1. **Never block the screen.** Saves run in the background; only the button shows progress; the user can keep working and move between pages.
2. **Show the change straight away.** If a save fails, undo it on screen and tell the user once.
3. **Never need a refresh.** Every save updates everything visible, in place.
4. **One clear message per problem**, in plain words: what happened and what to do next. Field problems go next to the field. Never error codes, stack traces, provider error text, or a pile of errors.
5. **Fast by default.** App servers run in the same region as the database; database work is batched (no per-row query loops); lists load as the user scrolls or searches instead of click-through pages; show a placeholder/skeleton while loading, never a blank wait.
6. **Long jobs** (imports, exports, clean-ups) run in the background with a progress notice and a done or failed notice.
7. **Works on phones and tablets.** Controls are reachable and accessible (touch targets, screen-reader labels, contrast, dynamic text size). The mobile apps work offline and sync (section 9).
8. **Before calling anything done**, check it at phone size and desktop size against this list and report what was checked.

## 4. Security rules
- Every tenant/account-owned read and write is enforced by **server authorization and database row-level security**, never by trusting an account/organization id sent by the client.
- Role-based access with least privilege (owner, admin, staff, customer, etc.). Test each role's allowed and forbidden actions.
- Money is stored as integer minor units (cents), timestamps in UTC, the account's timezone stored explicitly.
- Payments use the provider's hosted/collected flow; card numbers never touch our servers or logs.
- No secrets in code, logs, fixtures or client bundles. `.env.example` holds placeholders only. A secret-scanning hook runs before commit.
- Service-role/admin keys are never reachable from client code or mobile bundles.
- Never show provider error text to users on sign-up or sign-in (it can reveal whether an account exists).
- Customer-facing links use unguessable, expiring, revocable tokens; sequential or guessable ids are never authorization.
- Uploads: validate type and size, private buckets, signed short-lived URLs. **A limit on table rows is not a limit on storage**: enforce caps in the storage policy too, because a signed-in user can upload to storage directly.
- Webhooks: verify the signature on the raw body, de-duplicate by event id, match by exact object id.
- External AI/automation can never charge, message, delete or reschedule without an approved workflow and a confirm step. Stored or customer-supplied text is untrusted data, never instructions.
- Every chat/assistant box stays strictly on task: refuse off-topic, wrapped, indirect and "ignore your rules" requests every time. Tests for wrapped requests and prompt injection from stored text must pass before any AI switch is turned on. AI may only output a fixed-schema intent, not free text, and changes still need a confirm step.
- Treat every free-text input as hostile: plain-text rendering only, parameterised queries, header/email-injection guards, payload size limits, rate limits, spam/abuse controls.
- Audit-log sensitive actions. Historical facts (jobs, invoices, payments) are never silently overwritten.
- Sign-in hardening: two-step sign-in required for owners/admins with recovery codes; session idle timeout and a maximum session age; "sign out everywhere".
- Data lifecycle is written down and stated in the terms: photo/file retention setting, post-cancellation read-only + export period, then archive, then deletion (immediate on owner request).
- Keep a threat model document and update it when trust boundaries change.

## 5. Bug-hunt checklist (every build and every review, with a failing test for each item that applies)
Reading a diff for auth and RLS misses bugs that only appear over time. For each item, trace a concrete sequence and write the test that fails without the fix.
1. **Retries and double submits.** The same request twice (network retry, double tap, offline replay) must not double money or records. Use an idempotency key, and refuse a changed payload under the same key (do not report it done).
2. **Snapshot vs live.** Anything billed, totalled or reported uses the value at the time of the work (price, tax, name, plan), copied when the work happened, not today's value.
3. **Stale stored state.** Stored results (replays, conflicts, offline queues, cached decisions) are re-checked when the data behind them changes.
4. **Races.** Two concurrent requests against a limit, count or uniqueness rule are serialized (lock/transaction). Write the row before the upload; leave no orphans.
5. **External events.** Matched by exact object id (subscription, payment). Handle duplicates, out-of-order and same-second events.
6. **Caching.** Nothing signed-in, money, schedule or customer data lands in a shared cache.
7. **Whole flow, not just the diff.** Follow every money or data path the change touches end to end, including the older code it relies on.

Also: run a periodic whole-repo sweep with this list, not only per-PR; use a second, different reviewer on money/auth/data features when available. Reviews output a prioritized table: severity, file:line, reproducer, violated acceptance ID or control, minimal fix, verification test; then one line `MERGE: BLOCK` (any unresolved critical/high) or `MERGE: OK FOR HUMAN REVIEW`.

## 6. Caching rule
- Cache static assets and public marketing pages freely.
- Per-account slow-changing reference data (services, settings): cache only briefly, keyed by account, cleared on save.
- Never put money, schedules, customer data or any signed-in response in a shared cache: set `private, no-store` on authenticated pages and API routes.
- A mobile app's on-device copy is per person and is cleared on sign-out.

## 7. Open-source licence rule
Every dependency must allow commercial SaaS use. Run the licence check (`make licence-check`) as part of the main check script and whenever a package is added. Watch for AGPL, SSPL, GPL, no-licence and non-commercial licences. A failing package is replaced, or gets a reviewed entry with a reason in `licence-exceptions.json`. LGPL/GPL code is never bundled into mobile or downloadable builds (server-side use only, with legal review). Keep an inventory of third-party libraries and their licences.

## 8. Architecture and engineering
- **Modular monolith.** Shared core modules with a single entry point each and versioned contracts. Domain/vertical packs plug in through fixed slots. Module walls are enforced by automated import checks, not by convention.
- **Design for the real company**, not a demo: multiple business types, multiple legal entities per owner account with shared staff and separate money/books per entity, per-business feature switches. Never take a single-type or single-entity shortcut.
- **Per-business feature switches**, enforced server-side (never UI-only), "coming soon" when off; new features add a key in the same migration and the feature registry. Tiers/plans are bundles of switches.
- Build to 10,000-account principles; buy capacity only on evidence. Define uptime, recovery-point and recovery-time targets, run restore drills, load-test before launch, and report errors with alerts.
- **Background jobs** are retry-safe, idempotent, and visible when dead-lettered (job runs + alerts).
- **Migrations**
  - Timestamps must sort after every migration already on the main branch; renumber before merging if another branch landed first. Never edit a merged migration.
  - Every new database function: explicit `revoke ... from public, anon, authenticated, service_role`, then only the one grant it needs; `SECURITY DEFINER` functions set `search_path = ''`; add it to the data-API permission test if an app role can call it.
  - When restating an existing function, copy the newest migration's body, not the original.
  - When re-creating a table check that lists allowed values, keep every value added by earlier migrations.
  - New row-level-security policies use the once-per-query form (`org_id in (select helper(...))`, `(select auth.uid())`), never per-row function calls; a policy test enforces it.
  - A page must never fail because the newest migration has not run yet (previews are migrated by hand): read new tables through a "missing table" helper with a fallback that hides the section, guard writes with a plain "not available yet" error, and add a test that hides the table and renders the page.
  - Old backups and runbooks can reference schemas a migration drops; update the restore runbook in the same change.
- **Timestamps** passed from JavaScript to Postgres go as `${x}::text::timestamptz`; a direct `::timestamptz` cast makes the driver build a JS Date and drop microseconds, which skipped rows in cursors.
- **Links** on signed-in pages use the app's no-prefetch link component (lint-enforced); prefetching dozens of menu links queues in front of real clicks.
- **Seed/e2e data** is shared across specs that run in order: add data by natural key (`insert ... select ... where key = ...`), never by guessed ids.
- Seed and test fixtures use fake data only.

## 9. Mobile (iOS and Android)
Plan: one cross-platform codebase (not in scope, e.g. Expo/React Native) in its own repo, talking to the same backend through a versioned API contract generated from the server's schemas (e.g. OpenAPI from zod). Web/PWA first until the web pilot gates pass; store fees are paid only when the first pilot customer is ready (ask the owner first).

**Offline-first and sync**
- Real offline: a local database as the source for screens, a durable outbound queue, retry with backoff, de-duplication by client-generated idempotency keys, and explicit conflict states. Never claim offline works without testing queue, retry, dedup and conflict on real devices (airplane mode, flaky network, app killed mid-sync, clock skew).
- Queued actions are re-validated on sync when the underlying data changed (reassigned job, deleted customer, changed price); show the user a clear outcome, never silently drop or double-apply.
- Photos/files queue locally, upload with resumable/retriable requests, and are never lost on sign-out without warning.

**Secrets and storage**
- Tokens and refresh tokens live in the iOS Keychain / Android Keystore (encrypted storage), never in plain async storage, logs, or screenshots.
- No secrets in the app bundle: assume the bundle is public. Only publishable/anon keys; no service-role, signing or payment secret keys. Use short-lived tokens; the server enforces authorization on every request (RLS still applies).
- Encrypt the local database for sensitive data where the platform allows; clear all per-person local data on sign-out and on account removal. Exclude sensitive files from OS backups.
- Block screenshots/app-switcher previews on sensitive screens if the data warrants it; support biometric unlock as an optional layer, not a replacement for server auth.
- Support remote session revocation (server invalidates, app signs out on next contact) and a jailbreak/root-aware stance (do not rely on device integrity for authorization).

**Network**
- HTTPS only (App Transport Security / cleartext disabled). Consider certificate or public-key pinning for the API host: it blocks interception but breaks on certificate rotation, so pin to a key with a backup pin, ship a remote kill-switch/update path, and decide with the owner before enabling. Never pin to a leaf cert with no backup.
- Validate server responses; handle expired tokens and rate limits gracefully; no verbose network logging in release builds.

**Permissions and privacy**
- Ask for the minimum permissions, at the moment of use, with a plain-language reason (camera for job photos, location only while using the app for routes/arrival). Never request contacts, background location, or tracking unless a shipped feature needs it. The app must work (degraded) when a permission is denied.
- App Store privacy "nutrition labels" and the Google Play Data Safety form must match what the app and its SDKs really collect; update them in the same PR that changes collection. Keep a privacy policy and account-deletion path (both stores require in-app account deletion). Audit third-party SDKs for data collection and licence (section 7); fewer SDKs is better.
- Push notifications: use a provider approved by the owner; no sensitive details in the notification text; opt-in per category.
- Payments inside mobile apps: follow store rules for digital goods vs. real-world services; collect service payments through the hosted payment provider flow, never card fields we handle ourselves. Check store policy before choosing.

**Release and quality**
- Distinguish debug/staging/production builds and API hosts; production builds only through the owner-approved release step. Signing keys and store credentials are never in the repo; the owner holds them (put steps in `setup/owner-todo.md`).
- Version and build numbers increase every release; support a minimum-supported-version check so the server can force an upgrade after a breaking contract change.
- Crash and error reporting without personal data. Test on a small and a large phone, a tablet, a low-end Android, light and dark mode, large text, right-to-left and any supported languages, screen reader (VoiceOver/TalkBack).
- Beta through TestFlight and Play internal testing before any public release.
- Language support is per user; every screen is covered and untranslated text is not silently shown mixed.

## 10. Documentation and records
- Each finished feature or fix updates, in the same PR: its feature-map row, user story, roadmap row and the relevant runbook. Docs stay human-readable. Keep Markdown masters; export Word/PDF copies if needed.
- Record architecture decisions as numbered ADRs (what, why, alternatives).
- Maintain an architecture/system map and update it on any significant change (new component, service, job, data flow, trust boundary, or a planned item going live). Label items Live / Planned / Not connected truthfully; never show planned work as live.
- Update `docs/BUILD-STATUS.md` after each completed task with completed acceptance IDs and remaining failures.
- Track a north-star metric and keep it in docs.

## 11. Definition of done
Every linked acceptance criterion has evidence; format/lint, typecheck, unit, integration and end-to-end checks pass (report the actual commands and results; screenshots never count as functional verification); the bug-hunt checklist ran with tests; the licence check passes; the experience standard was checked at phone and desktop size (and on a real device for mobile); docs are updated; rollback is possible; an independent security review found no unresolved critical/high; and the owner approves release. Never skip tests to speed a milestone.

## 12. Execution protocol for a task
1. Inspect the current tree, package scripts, recent changes and tests.
2. Write a concise plan naming files and acceptance IDs.
3. Make a small, reviewable diff; no unrelated refactors.
4. Add migration, tests, docs and telemetry where relevant.
5. Run the checks and report actual results.
6. Independent review in a fresh context (security, QA, code quality). Reviewer judges the actual diff and tests, not the author's summary.
7. Fix findings with tests, then merge per the owner's rule (human merges and approves releases unless the owner has delegated merging).

## 13. Tooling for Claude Code (suggested `.claude/` setup)
- Hooks: secret guard before commit, format/lint on edit, typecheck on stop, session-start summary of branch, uncommitted changes and build status.
- Read-only subagents: `security-reviewer` (strongest model; org boundary, RBAC/RLS, secrets, payments, links, recurrence/time, uploads, AI paths + the section 5 checklist) and `qa-verifier` (lighter model; reproduces builds/tests and checks each claimed acceptance criterion).
- Skills: implement-task, review-branch (parallel security + QA + quality reviewers merged into one table), signoff-card (approval note for anything needing the owner).
- Permissions: exact-only allow rules (named scripts, specific read-only git commands). Do not add wildcard/prefix allows; every review round found a new write bypass through them.
- CI: if CI minutes are limited, the merge gate is local checks plus independent security review, with browser e2e run on a schedule.

## Lessons (add one line whenever a mistake or review finding could repeat)
- Never present a simulated capability (e.g. a vision model that does not exist) as live; label it or remove it.
- Never commit real player or club names, even as "synthetic profiles".
- Never trust the Host header for origin checks; only listed origins.
- Pass `TemplateLLM()` explicitly wherever paid model calls are not allowed; `llm=None` follows the AI switch.
- When the roster in `teams.py` changes, regenerate `backend/data/matches` or the dataset check fails.
- In a multi-line CI `run:` block, `! grep ...` fails the step only on the last line (bash -e ignores negated commands); use `if grep ...; then exit 1; fi`.
- Key rate limits and connection caps on the last X-Forwarded-For entry (added by the ingress), never the first; and keep paid per-request work (translation) off routes anyone can loop on.
- Persona voices use only stats we compute: no game points, bonus systems or real-league fantasy branding (the "Stats scout" persona keeps the API value `fantasy`).
- Feed input is untrusted even when it is well-formed: type and range-check every value other code reads (scores, enums), take numbers for facts from the stats engine, and keep live appends all-or-nothing.
- An all-or-nothing rollback restores every structure the step writes (samples, indexes, checkpoints, side state), and its test fails late in the step, not first.
- A per-connection limit is not a limit on shared state: anything every viewer shares (the playback clock, process memory across send queues) needs a cap for the whole process, sized against the container.
