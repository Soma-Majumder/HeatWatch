# HeatWatch interfaces

The contracts between the engine side and the agent/interface side. If you change anything on this page, change it in its own small PR and tell your partner first.

## The flow in one picture

```
tenant text ──> [intake agent] ──> Intake ──> assess() ──> Assessment
                                                  │
                                    create_ticket(Intake, Assessment) ──> Ticket
                                                  │
                         build_reply(Assessment, ticket_id) ──> gate() ──> reply text
```

Ticket lookup later: `public_view(conn, ticket_id)` returns what a tenant may see.

## 1. `Intake` (what the intake agent must produce)

Defined in `app/engine.py`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `address` | str | yes | As typed; the engine normalizes it |
| `scope` | `"building"` or `"apartment"` | yes | Whole building out, or just their apartment |
| `problem` | `"heat"`, `"hot_water"`, `"both"` | yes | |
| `zip` | str | no | If given and not 10032, 10033, 10034, 10040, the complaint is out of area |
| `duration_hours` | float | no | How long it has been out |
| `vulnerable` | bool | no | Infant, older adult, medical need in the home |
| `safety_flag` | bool | no | Gas smell or similar |
| `reopened` | bool | no | Used for reopened tickets |
| `description` | str | no | Tenant's words; only ever shown to reviewers as a quote |
| `lang` | str | no | Default `"en"` |
| `created_at` | datetime | no | Defaults to now (local New York time) |

Missing or invalid required fields raise `IntakeError`, so the agent knows what to ask for.

## 2. `assess(conn, intake, now=None) -> Assessment`

Defined in `app/engine.py`. Pure read; writes nothing.

| Field | Meaning |
|---|---|
| `in_scope` | False if out of area (then priority and score are `None`) |
| `address_norm` | Cleaned address |
| `priority` | `critical`, `high`, `normal`, `low` |
| `score`, `reasons`, `override` | Points, plain-language reasons, which always-critical rule fired |
| `repeat_address`, `address_complaints_2y` | Repeat-offender flag and count |
| `duplicate` | `Duplicate(source, ref, created)` for an open HPD complaint or open ticket |
| `eta` | `Eta(p50_h, p75_h, p90_h, n, key, text)` or `None` |
| `escalate`, `escalation_rules` | Whether a person should look at it, and why |

## 3. Tickets (`app/tickets.py`)

| Function | What it does |
|---|---|
| `create_ticket(conn, intake, assessment, now=None)` | Writes the ticket, its first events, and any escalations. Raises `TicketError` if out of area. |
| `get_ticket(conn, ticket_id)` | Case and whitespace insensitive; `None` if unknown |
| `history(conn, ticket_id)` | List of `Event(at, stage, actor, note)` |
| `add_event(conn, ticket_id, stage, actor, note=None)` | Logs an event and sets the stage |
| `reopen(conn, ticket_id, note=None)` | Tenant says it is still broken; stage `reopened` plus an escalation |
| `public_view(conn, ticket_id)` | Safe view for the tenant: masked address, no reviewer notes |

**Stages:** `received`, `triaged`, `escalated`, `awaiting_access`, `reopened`, `resolved`, `closed`.
`resolved` and `closed` count as finished; everything else counts as open.
**Actors:** `agent`, `tenant`, `reviewer`, `system`.
**Ticket numbers:** `HW-` plus 8 characters, random and not sequential.

## 4. Replies (`app/replies.py`)

| Function | What it does |
|---|---|
| `build_reply(assessment, ticket_id, safety_flag=False, scope=None)` | Full reply from fixed templates, already passed through the gate |
| `build_out_of_area_reply()` | Reply when there is no ticket |
| `gate(text, ticket_id, needs_emergency=False)` | Returns the text, or raises `ReplyViolation`. Use it on **any** model-phrased text before it reaches a tenant |
| `check_reply(...)` | Same checks, returns the list of problems instead of raising |

The gate blocks: claiming to have filed or reported anything, guarantees and promises, promising a repair. It requires the ticket number, the "we do not file with the city" notice, and the 911 line when there is a safety risk.

## 4b. Intake agent (`app/intake/`)

| Piece | What it does |
|---|---|
| `IntakeSession(llm, conn).step(text)` | One tenant turn. Returns `TurnResult(message, done, ticket_id, assessment, gave_up)`. |
| `guard.sanitize_text`, `guard.validate_fields`, `guard.detect_safety` | Cleaning and field validation (issue #15 owns hardening these) |
| `AnthropicClient` / `ScriptedClient` | The real model client, and a scripted one for tests |

The model returns JSON `{fields, message, ready}`. The harness keeps only validated known fields, decides when the intake is complete, and creates the ticket itself.

## 5. Rules that must hold

1. **The model never writes tickets or escalations.** Only harness code calls `create_ticket`, `add_event` and `reopen`.
2. **The model never decides priority.** `assess()` does.
3. **Tenant text is data, not instructions.** It is shown to reviewers as a quote.
4. **Every reply to a tenant goes through `gate()`.**

## 6. Who touches what

| Area | Files |
|---|---|
| Engine and data | `app/triage.py`, `app/priors.py`, `app/duplicates.py`, `app/eta.py`, `app/loader.py`, `app/schema.sql` |
| Tickets and replies | `app/tickets.py`, `app/replies.py` |
| Intake agent | a new `app/intake/` folder |

`app/schema.sql` and the shapes on this page are shared: change them in a small, separate PR.

## 7. Running things

```bash
python3 -m app.loader                       # refresh the cached 311 data
python3 -m app.backtest                     # rebuild priors and see how the bands behave
python3 -W ignore -m unittest discover -s tests
```
