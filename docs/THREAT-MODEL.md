# Threat model

What PitchPulse protects, where the trust boundaries are, what can go wrong on
each surface, what stops it, and which tests prove the control. Update this
page whenever a trust boundary changes (a new endpoint, a new external service,
sign-in, uploads, a new model path). System map: [ARCHITECTURE.md](ARCHITECTURE.md).

Last reviewed: 22 Oct 2026, on the integration branch with every feature
merged. Test files below are in `backend/tests/` unless a path says otherwise.

## Scope and assumptions

- **No accounts, no personal data, no payments, no uploads.** Everything the
  app serves is public synthetic match data. A viewer's profile (persona,
  language, club, catch-up) lives on their connection and in their own browser
  storage, never on the server.
- **Anyone on the internet can call every route.** There is no sign-in on
  purpose; every control below assumes a hostile caller.
- **Nothing is deployed yet.** Azure controls are in the Bicep template and
  tested in CI (build, lint, "no keys in outputs"), not in a running
  subscription.

## Assets

| Asset | Why it matters |
|---|---|
| Correctness of on-air numbers | The product's promise: every number comes from the stats engine (ADR 0001) |
| The shared match clock | One clock for every viewer (ADR 0006); moving it moves everyone |
| The owner's Azure spend | Model tokens and Translator characters are billed |
| Availability of the live session | One replica serves every viewer |
| Brand and data rules | No real clubs, players or broadcasters may appear, whatever a feed or a model says |
| Azure credentials | None exist as keys; managed identities only. Their scope must stay minimal |
| The repository | No secrets, no real names, licences that allow commercial use |

## Trust boundaries

1. Browser to REST API (`/api/*`).
2. Browser to WebSocket (`/ws/match`).
3. MCP client to `/mcp` (and the local stdio server).
4. Free text: the Ask box (`POST /api/ask`, MCP `ask_studio`).
5. Data out: dataset export (`/api/dataset*`).
6. Data in: feed files and the Event Hubs stream.
7. App to Azure OpenAI / Foundry Agent Service.
8. App to Azure AI Translator.
9. Served pages in the browser (CSP).
10. CI/CD to Azure (OIDC).

## Threats and mitigations

### REST API

| Threat | Mitigation | Evidence |
|---|---|---|
| Cross-site use from an unlisted origin | CORS allow-list from `MATCHMIND_ALLOWED_ORIGINS`, no credentials, no `*` | `test_api.py::test_cors_allows_listed_origin_and_rejects_others` |
| Flooding routes that can spend (moment, recap, audit, cue sheet, Ask) | Per-IP token buckets; client IP is the last `X-Forwarded-For` entry, so a spoofed header buys nothing | `test_api_security.py::test_routes_that_can_call_the_translator_are_limited_per_ip`, `::test_spoofed_forwarded_for_does_not_buy_a_fresh_bucket`, `::test_post_routes_are_limited_per_ip` |
| Seek/speed/reset storms moving the shared clock | Shared throttle across REST and WebSocket; one seek per burst | `test_api_security.py::test_ws_seek_burst_runs_once_and_playback_goes_on`, `::test_rest_seek_burst_gets_429_and_shares_the_throttle_with_ws` |
| Bad seek values | Closed request models and range checks | `test_session.py::test_seek_rejects_bad_times` |
| Shared caches holding live responses | `Cache-Control: no-store` on every `/api` route except dataset downloads (public synthetic files) | `test_dataset.py::test_api_other_routes_stay_no_store`, `test_ask.py::test_rest_answers_and_never_caches` |
| Leaking spend counters | Translator and model spend stay inside the server | `test_api_security.py::test_public_payloads_carry_no_translator_spend_counters` |
| Slow crew work stalling playback | Crew work off the playback path; translator called with no lock held | `test_api_security.py::test_slow_crew_work_does_not_block_playback_controls`, `::test_world_language_recap_is_translated_without_the_crew_lock` |

### WebSocket

| Threat | Mitigation | Evidence |
|---|---|---|
| Connection from an unlisted origin, or trusting `Host` | Origin allow-list; the server's own public origin only when it serves the frontend; `Host` is never trusted | `test_api.py::test_ws_rejects_unlisted_origin`, `::test_ws_allows_listed_origin_and_never_trusts_host`, `::test_ws_allows_own_public_origin_only_when_serving_the_frontend` |
| Oversized or malformed messages | Size cap, every action validated | `test_api.py::test_ws_oversize_message_rejected` |
| Many connections from one IP | Per-IP connection cap; slots reserved before accept | `test_api_security.py::test_connections_are_capped_per_ip`, `::test_slots_are_reserved_before_accept` |
| A slow reader exhausting memory | Bounded send queue in bytes; overflow closes the connection | `test_api_security.py::test_send_queue_overflow_really_closes_the_connection`, `::test_send_queue_counts_bytes_and_frees_them_when_sent` |
| `set_view` storms forcing cue-sheet rebuilds | Per-connection limit; bounded incremental cue compiles per tick | `test_cue_load.py::test_set_view_is_rate_limited_per_connection` |
| Action rate | Per-connection token bucket | `test_api.py::test_ws_rate_limit`, `::test_rate_limiter_refills` |

### MCP

| Threat | Mitigation | Evidence |
|---|---|---|
| A tool that changes the match | Every tool is read-only; none plays, seeks or resets | `test_mcp.py` contract snapshot (`snapshots/mcp_tools.json`) |
| DNS rebinding / cross-site calls | Browser `Origin` must be listed; `Host` must be localhost, a listed or public origin's host, or in `MATCHMIND_MCP_ALLOWED_HOSTS` (never a wildcard) | `test_mcp.py::test_allowed_origin_is_served_and_other_origins_refused`, `::test_unknown_host_is_refused_against_dns_rebinding`, `::test_allowed_hosts_never_include_a_wildcard` |
| Large bodies, batches that dodge the rate limit | 16 KB cap, JSON-RPC batches refused, own per-IP bucket | `test_mcp.py::test_oversized_body_is_refused`, `::test_batches_are_refused`, `::test_per_ip_rate_limit` |
| CPU abuse through `simulate_match` | Cache of 64 seeds, one simulation at a time, server-wide rate, 10,000-event cap | `test_mcp.py::test_simulation_is_cached_and_rate_limited` |
| Error details leaking | One plain sentence; details stay in the server log | `test_mcp.py::test_a_crash_never_leaks_details` |
| REST and MCP disagreeing | One accessor (`api/reads.py`); byte-parity test per tool | `test_mcp.py` parity cases |
| Local client spending on paid AI | stdio server pins the crew to templates even with the AI switch on | `test_mcp.py::test_stdio_entry_point_serves_the_tools` |

### Ask the studio (free text)

| Threat | Mitigation | Evidence |
|---|---|---|
| Prompt injection, wrapped or indirect "ignore your rules", role-play | Guard refuses override phrasing in en/es/fr/ar after normalisation (NFKC, look-alikes, spacing); rule parser maps to fixed intents; answers are templates | `test_ask.py::test_adversarial_questions_are_refused` (37 inputs), `::test_refusals_say_why_in_one_plain_sentence` |
| Markup, script, SQL, bidi or zero-width characters | Guard refuses; the web app renders text only | `test_ask.py` adversarial set; `frontend/src/components/askCatchUp.test.tsx` |
| Real names or a crafted squad name | Banned list; names resolved only against this match's squads; never echoed | `test_ask.py::test_crafted_player_name_is_never_echoed_or_obeyed` |
| Model writing the answer | Model (AI switch on only) may return only `IntentGuess` JSON; ids resolved by our code; model text never shown | `test_ask.py::test_model_path_is_never_asked_about_refused_or_parsed_questions`, `::test_ai_switch_off_means_no_model` |
| Spoilers or future events | Answers read the engine as of the clock; catch-up hides result intents | `test_ask.py::test_answers_never_read_past_the_clock`, `test_spoilers.py` |
| Question text in logs | Logs keep status, reason, intent and length only | `test_ask.py::test_question_text_is_never_logged` |
| Oversized bodies, unknown fields | 2 KB body, 1000 characters per field, 200 answered, unknown fields refused; shared rate limit | `test_ask.py::test_rest_rejects_bad_bodies`, `::test_rest_long_question_is_a_plain_refusal`, `::test_rest_is_rate_limited_with_the_get_bucket` |
| A wrong number in an answer | Every sentence fact-checked; any failure replaces the whole answer with a refusal | docs/ASK.md; `test_ask.py` |

### Dataset export

| Threat | Mitigation | Evidence |
|---|---|---|
| CSV formula injection in spreadsheets | Text cells never start a formula | `test_dataset.py::test_csv_text_cells_never_start_a_formula` |
| Expensive exports as a denial of service | Own per-IP bucket, bounded build slots, tracking window limits | `test_dataset.py::test_api_export_is_rate_limited_per_ip`, `::test_api_export_refuses_when_every_build_slot_is_busy`, `::test_tracking_window_limits` |
| Bad parameters | Plain-words refusals | `test_dataset.py::test_api_export_refuses_bad_requests_in_plain_words` |
| Cached downloads | Allowed on purpose: public synthetic files only; every other `/api` route is `no-store` | `test_dataset.py::test_api_other_routes_stay_no_store` |

### Feed ingest and Event Hubs

| Threat | Mitigation | Evidence |
|---|---|---|
| Malformed or hostile feed (sizes, shapes, clocks, speeds) | One validator for every door: size caps, schema enums, clock order, finite numbers, pitch bounds | `test_ingest.py::test_size_caps`, `::test_clock_running_backwards_is_refused`, `::test_infinite_speed_is_refused`, `::test_naive_timestamps_are_refused` |
| Real or odd names smuggled in | Banned list, name shape checks, roster size cap | `test_ingest.py::test_roster_rejects_real_or_odd_names`, `test_live_source.py::test_a_match_start_with_real_names_is_refused` |
| Players not in the line-up | Every reference checked against line-up and team | `test_ingest.py::test_player_not_in_the_line_up_is_refused`, `::test_player_in_the_wrong_team_is_refused` |
| Redelivery, reordering, changed content under the same seq | Dedup by seq, reorder buffer, first version stands, gaps skipped after 5 s | `test_live_source.py::test_same_seq_with_changed_content_is_refused_and_the_first_stands`, `::test_a_gap_that_never_fills_is_skipped_after_the_timeout` |
| A feed-supplied score becoming a fact | Scores always from the engine; a bad score is rejected and the match stays whole | `test_live_source.py::test_a_feed_supplied_score_never_becomes_a_fact`, `::test_a_bad_score_in_the_stream_is_rejected_and_the_match_stays_whole` |
| Uploads replacing everyone's match | No upload endpoint; feeds are operator files (docs/DATASET.md) | Route list in `api/app.py` |
| Keys for Event Hubs | Keyless only (`DefaultAzureCredential`); no connection-string path | docs/DATASET.md |

### Azure OpenAI and Foundry Agent Service

| Threat | Mitigation | Evidence |
|---|---|---|
| Unapproved spend | One AI switch, off by default; places that must never spend are pinned to templates; per-process budget and per-minute rate | `test_crew.py::test_make_llm_is_template_unless_switched_on`, `test_session_security.py::test_loading_the_match_never_calls_the_paid_model`, `test_foundry.py::test_dataset_never_calls_paid_ai_even_with_the_switch_on`, `test_crew_budget.py` |
| A model inventing a number or name | Fact-checker gate; template fallback; rejected names never reach the trace | `test_crew.py::test_unbacked_number_from_model_is_rejected_and_template_used`, `::test_model_number_word_falls_back_to_template`, `::test_rejected_name_never_reaches_the_trace`, `test_foundry_agent_service.py::test_fact_checker_rejects_an_agents_unbacked_number` |
| Slow or failing provider | Timeout, one repair retry, circuit breaker, fallback with a reason | `test_crew.py::test_timeout_falls_back_to_template_and_is_traced`, `test_foundry_agent_service.py::test_timeout_falls_back_to_the_template_with_a_reason` |
| Provider error text reaching viewers | Never shown or logged | `test_foundry_agent_service.py::test_provider_errors_never_carry_provider_text` |
| Prompt injection through model input | Models receive only engine facts as JSON, never viewer text (Ask's model intent sees the guarded question and may return only a fixed schema) | docs/FOUNDRY.md, docs/ASK.md |
| A registered agent with a changed prompt | Agent prompt must match the card; unknown schemas refused | `test_foundry_agent_service.py::test_a_prompt_that_differs_from_the_agent_is_refused_and_unknown_schemas_too` |
| Over-broad roles | App identity: Cognitive Services OpenAI User on the resource; Azure AI User on the project only with `foundry_agents` | `deployment/azure_bicep/main.bicep`, docs/FOUNDRY.md |

### Azure AI Translator

| Threat | Mitigation | Evidence |
|---|---|---|
| A translation changing a number or name | Protected spans must round-trip exactly; fact-checked again; English fallback | `test_translator.py` |
| Spend | Separate switch on top of the AI switch; character budget and per-minute rate; one request for many viewers; bookmark pass never translates | `test_translator.py`, `test_foundry.py::test_evaluation_never_translates_even_with_both_switches_on` |
| Keys | Custom subdomain plus Entra token; the client refuses any other endpoint | `test_translator.py::test_only_a_custom_subdomain_endpoint_is_used` |

### Served pages (browser)

| Threat | Mitigation | Evidence |
|---|---|---|
| Script injection | CSP: `script-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'none'`; all text rendered as text, never HTML | `test_api.py::test_pages_carry_a_content_security_policy_and_api_routes_do_not` |
| Clickjacking | `frame-ancestors 'none'` (OBS and vMix load the page as a top-level browser source) | same test |
| Downgrade | HSTS when the public origin is https | `test_api.py::test_hsts_only_when_the_public_origin_is_https` |
| Links that pin a profile overwriting saved choices | Link values are checked and never saved | `frontend/src/state/useMatch.test.ts` |

### CI/CD and repository

| Threat | Mitigation | Evidence |
|---|---|---|
| Secrets in the repo | gitleaks over full history in CI; no keys exist to leak | `.github/workflows/ci.yml` (Secret scan) |
| Keys in deployment outputs | CI fails on `listKeys`, connection strings or key-like output names | `.github/workflows/ci.yml` (Template outputs no keys) |
| Deploy identity abuse | OIDC, `production` environment approval, `main` only; may grant only the roles the template uses (role-assignment condition) | `setup/owner-todo.md`, `.github/workflows/deploy.yml` |
| Copyleft dependencies | Licence check in `make check` and CI | `Makefile` (`licence-check`) |
| Container running as root | Image runs as non-root (checked in CI) | `.github/workflows/ci.yml` |

## Residual risks

- **No sign-in.** Anyone can move the shared clock (rate limited) and read
  everything. Acceptable for public synthetic data; any write or private data
  needs sign-in first.
- **One replica.** A crash drops every viewer until the container restarts.
- **Fact-checker scope.** Tone, causal wording, negation and player-level
  attribution are not machine-checked (docs/TRUST.md). A model could print a
  true number with the wrong meaning when the units match.
- **Model path not measured live.** All quality numbers are template mode.
- **Ask guard is rule-based.** It covers en, es, fr and ar phrasing; an unknown
  name in Arabic or Japanese script is not detected as a name.
- **Azure controls are untested against a live subscription.** They are
  template-checked only until the owner deploys.
- **Rate limits are per process.** They reset on restart and are not shared
  across replicas (there is one replica).
