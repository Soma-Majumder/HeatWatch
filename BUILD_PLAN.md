# HeatWatch Build Plan

Status: draft for review. Nothing in this plan has been built yet.
Source of truth for scope: `HeatWatch PRD.docx` (P0/P1/P2 requirements).

## 1. What we are building

A single-role AI triage agent for HEAT/HOT WATER complaints in Washington Heights and Inwood (Manhattan Community Board 12). It runs the loop from the PRD:

| Loop stage | What the system does |
|---|---|
| Observe | Takes a complaint in chat, enriches it with address history from 2 years of HPD data and our own tickets |
| Decide | Scores urgency, detects duplicates, picks the route (reply only, escalate to human, emergency referral) |
| Act | Creates a ticket number, replies with urgency, ETA and next step |
| Feedback | Records ticket events and outcomes; tenant looks up progress by ticket number |
| Loopback | Re-triages overdue, repeat and reopened tickets; compares quoted ETA with actual close time and recalibrates |

Out of scope (per PRD non-goals): filing with HPD/311, other boards or boroughs, NYCHA, legal advice.

## 2. Proposed stack (defaults, change if you disagree)

| Concern | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Simple, good for data work and async calls |
| Storage | SQLite (file DB) | One-process MVP; schema portable to Postgres later |
| LLM | Claude (`claude-sonnet-5-5`) for intake conversation and reply wording | Language handling (incl. Spanish) and plain-language replies |
| Triage logic | Plain deterministic Python, not the LLM | Auditable, testable, repeatable; LLM only extracts fields and phrases replies |
| Front end | One small HTML/JS chat page + ticket lookup page + reviewer queue page | Covers all three PRD journeys without a framework |
| Jobs | APScheduler (in-process) | Daily data refresh, hourly overdue sweep |
| Tests | pytest, plus an offline backtest harness | See section 7 |

## 3. Data model

```
tickets            id (HW-XXXXXX), created_at, address_norm, address_raw, zip,
                   scope (building|apartment), problem (heat|hot_water|both),
                   duration_hours, vulnerable, safety_flag, description,
                   priority (critical|high|normal|low), score, score_reasons (json),
                   stage, eta_hours, linked_311_key, duplicate_of, lang
ticket_events      id, ticket_id, at, stage, actor (agent|tenant|reviewer|system), note
escalations        id, ticket_id, rule, reason, at, status (open|ack|closed), reviewer
address_stats      address_norm, complaints_2y, last_complaint_at, repeat_flag
priors             key (scope|month|hour_bucket), n, p50_close_h, p75, p90, dup_rate
hpd_complaints     cached copy of source rows (unique_key, created, closed, status, ...)
```

Ticket IDs are `HW-` plus a random, non-sequential suffix so a ticket number is hard to guess (it is the only lookup credential).

## 4. Triage engine (Decide)

Initial scoring, to be tuned in the backtest (section 7). These weights are starting assumptions, not findings.

| Signal | Points |
|---|---|
| Whole building | +3 (apartment only +1) |
| Heat season (Oct 1 to May 31) | +2 |
| Outage > 24h / > 48h | +2 / +3 |
| Vulnerable household | +3 |
| Overnight report (10pm to 6am) | +1 |
| Repeat-offender address | +2 |
| Reopened ticket | +2 |

Priority bands: critical ≥ 8, high 5–7, normal 2–4, low < 2.
Hard overrides: any safety flag, or vulnerable household with no heat in heat season, is `critical` and goes straight to escalation plus the emergency-services message.

Duplicate detection: normalize the address, then look for an active HPD complaint (open, created within the last N days, since some "Open" rows are stale) or an open HeatWatch ticket. Link instead of creating a competing ticket; still give the tenant their own ticket number.

ETA: from `priors` by scope and season (baseline median about 42h, p90 about 84h), quoted as a range.

Escalation rules (from PRD appendix): safety or vulnerable no-heat, whole-building outage in heat season, overdue past quoted window, reopened, repeat-offender address, low confidence or out of scope.

## 5. Build phases

Each phase ends in something demonstrable and maps to PRD requirements.

| Phase | Deliverable | PRD coverage |
|---|---|---|
| 0. Foundation | Repo layout, config, SQLite schema, data loader that pulls the CB12 2-year dataset (`fbiz-gkhq`, ~40,690 rows) and caches it | Constraints, data source |
| 1. Priors + triage engine | Address normalization, `priors` and `address_stats` build, scoring, duplicate check, ETA, unit tests | J1 Decide (P0), duplicate and ETA |
| 2. Intake agent | Claude-driven conversation that extracts address/ZIP, scope, problem, duration, vulnerable; out-of-area handling; 24/7 | J1 Observe (P0/P1), Spanish (P1) |
| 3. Tickets + replies | Ticket creation, reply templates built from the six HPD outcome types, safety message, "we do not file with HPD, use 311" message | J1 Act (P0) |
| 4. Tracking | Lookup by ticket number, stage history, latest reply; tenant can confirm fixed, report still broken (reopen), add access times | J2 (P0/P1) |
| 5. Reviewer queue | Ranked open tickets, overdue flag, escalation alerts with reason, priority override with reason, repeat-offender view | J3 Reviewing (P0/P1) |
| 6. Loopback | Hourly overdue/repeat re-triage, ETA-vs-actual report, daily priors refresh, reopen handling | J3 Improving (P0/P1) |
| 7. Hardening | Privacy review, rate limiting, logging, load check at 150 complaints/day peak, pilot checklist | Metrics, risks |

P2 items (photo/thermometer upload, status notifications, data export) are deferred until P0/P1 are done.

## 6. Interfaces

HTTP API (FastAPI):

| Endpoint | Purpose |
|---|---|
| `POST /complaints` | Chat turn(s) that produce a triaged ticket |
| `GET /tickets/{id}` | Stage, history, latest reply, ETA status |
| `POST /tickets/{id}/followup` | Confirm fixed, report still broken, add info |
| `GET /review/queue` | Ranked open and overdue tickets, escalations |
| `POST /review/{id}/override` | Change priority with a recorded reason |

Scheduled jobs: daily 311 refresh (`priors`, `address_stats`), hourly overdue sweep.

## 7. Testing and evaluation

- **Unit tests:** scoring bands, hard overrides, duplicate linking, address normalization (e.g. "516 WEST  156 STREET" variants), ETA lookup.
- **Backtest on the 40,690 historical rows:** run the scorer over past complaints and check that high/critical bands concentrate the slow-to-close and access-failed cases. Tune weights until the top bands lift over the baseline. This is how the starting weights in section 4 get replaced with evidence.
- **Conversation evals:** a fixed set of scripted tenant messages (clear, vague, out-of-area, Spanish, safety risk, abusive, off-topic) with expected extracted fields and expected route.
- **Safety tests:** gas smell and CO mentions must always trigger the emergency message; the agent must never claim it filed anything with HPD.
- **PRD metric checks:** reply within 2 minutes, escalation within 15 minutes, duplicate flag rate ≥ 90% against HPD's own duplicate label (held-out data).

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Agent implies it filed with HPD | Fixed disclaimer in every first reply; tested |
| Wrong urgency on a real emergency | Hard overrides in code, not LLM judgment; human escalation |
| Ticket number as only credential | Non-guessable IDs, minimal data on lookup, rate limiting |
| Tenant address is personal data | Store only what is needed, retention limit, no addresses in logs |
| Stale "Open" rows in source data | Only treat recent opens as active; show source date |
| NYCHA buildings misrouted | Ask the question at intake; route to NYCHA channel; ownership join is a later option |
| Winter surge (~20x summer) | Deterministic triage path is cheap; LLM used only for intake and wording; load test in phase 7 |
| Low LIC-style sample sizes if scope widens | Not in scope now; priors are keyed so other areas can override |

## 9. Decisions (defaults adopted)

These were open; the team chose to proceed with defaults. Revisit any of them before the phase that depends on it.

| # | Decision | Default adopted | Revisit before |
|---|---|---|---|
| 1 | Human reviewer and notification | HeatWatch operator, reviewed through the reviewer queue dashboard only (no email/SMS). Still an open question in the PRD. | Phase 5 |
| 2 | Tenant channel for MVP | Web chat only | Phase 2 |
| 3 | Hosting | Local demo only; not exposed to real tenants | Phase 7 |
| 4 | Privacy | Store only the address, ticket details and events; no addresses in logs; 90-day retention proposed | Phase 7 |
| 5 | Spanish | Included as P1, built in phase 2 after the P0 intake flow works in English | Phase 2 |
| 6 | Repo layout | App under `/app`, with the PRD and this plan at the repo root | Phase 0 |

## 10. Definition of done for the MVP

All PRD P0 requirements pass their tests, the backtest shows the priority bands are meaningfully better than random, and a scripted end-to-end demo works: report, triage, ticket number, lookup, escalation alert, reviewer override, reopen, and re-triage.
