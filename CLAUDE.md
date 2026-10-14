# HeatWatch

HeatWatch is a read-only research agent. It answers questions about NYC heat and hot water
complaints using public 311 data, choosing each next analysis from what the last result showed.
Every number in its answer traces back to the query that produced it.

Builders: Dikshyant and Soma. Goal: a portfolio piece online in 4 days. We know some Python.
- Write the agent loop by hand. No agent frameworks (no LangChain, LlamaIndex, CrewAI, Tool Runner).
- Keep files small; comment anything non-obvious; explain code to us when we ask.
- Work ONE day-plan step at a time. At the end of each, STOP and show the "done when" check.
- Never start the next day's work without being asked.

Design docs live in docs/: HeatWatch-Agent-Blueprint.md (the full, longer design),
HeatWatch-Technical-Choices.md (model, stack and module choices with reasons), and two HTML pages
for humans. Read them for background. Where they differ from this file (the blueprint plans
about 10 days; this file is the 4-day version), THIS FILE WINS.

## Decisions (14 Oct 2026)

- Model: Claude through the Anthropic API (`anthropic` Python SDK), tool calling.
  Default `claude-haiku-4-5-20251001`; one comparison run on Sonnet 5.5 on Day 3.
  Model id comes from `.env` (`HEATWATCH_MODEL`), never hard-coded.
- Web page: Streamlit (`app.py`), hosted on Streamlit Community Cloud from GitHub.
- Weather: Open-Meteo historical API (no key, non-commercial use),
  `https://archive-api.open-meteo.com/v1/archive`, NYC lat 40.7829, lon -73.9654 (Central Park).
  Heating degree days computed in code: sum over days of max(0, 65 - daily mean °F).
- Input validation: pydantic models; the same models produce the JSON schemas sent to Claude.
- Storage: SQLite (stdlib `sqlite3`) for ledger + cache; JSONL files for traces.
- Briefing shows counts only; building addresses go in a separate list in the UI.
- Python 3.12. Tests with pytest.
- Demo limits: 20 questions/day total, 3 per visitor session; 3 saved example answers shown
  without calling the API.

## Secrets

- `ANTHROPIC_API_KEY` lives ONLY in `.env` (local) or Streamlit secrets (deployed).
- `.env` is in `.gitignore` from the first commit. Never print, log or commit the key.
- Do not export the key in the shell profile: Claude Code may offer to use an `ANTHROPIC_API_KEY`
  environment variable for itself, which would bill the project key.

## Hard rules (enforce in code AND test them)

1. All tools are read-only. No tool writes to any outside system.
2. The model never does arithmetic. Tools return counts, changes, percents and shares.
3. Every successful tool result goes into the ledger: id, tool, exact query, fetched_at, result.
4. `compare_periods`, `count_buildings` and `get_temperature` are refused (PRECONDITION)
   until `check_coverage` has passed for the periods used.
5. Budgets per run: 12 steps, 8 data queries, 4 skill loads, 120 s, cost cap from `.env`.
   Checked before EVERY model call and tool call. On a budget hit: partial findings, labeled.
6. Exactly one tool call per turn (tool_choice "any", parallel tool use disabled). A run ends
   only via `submit_briefing` or a runtime stop. Statuses: answered, cannot_answer,
   needs_clarification, out_of_scope, budget_exhausted, source_unavailable.
7. Claim check before any briefing is shown:
   - every number matches a cited ledger value, or a sum of cited values; percents compared
     rounded to whole numbers; counts exact, or nearest hundred if prefixed "about";
   - building claims cite a count_buildings entry; weather claims cite get_temperature;
   - if total change > 10% and status is answered, a get_temperature entry must exist
     (or cannot_tell explains why not);
   - no causal/blame wording ("because", "caused by", "failing to", "neglect", "fault");
   - no street addresses in briefing text; `cannot_tell` non-empty.
   Fail -> one rewrite with the exact failures. Fail again -> drop failing sentences, say so.
8. Errors return a structured tool result: {error, retryable, message, suggestion}.
   Codes: INVALID_ARGS, PRECONDITION, TIMEOUT, SOURCE_ERROR, REPEAT_CALL.
   Transient 5xx: runtime retries once after 2 s. TIMEOUT goes back to the model (it narrows).
9. Same tool + same arguments twice in a run -> REPEAT_CALL with the cached result, counts a step.
10. Queries are built only from validated, enum-checked parameters, never from model free text.
11. Every run writes a JSONL trace. Never log the API key.

## Data source

NYC 311 Service Requests (Socrata) `https://data.cityofnewyork.us/resource/erm2-nwe9.json`

Confirmed 8 Oct 2026:
- `complaint_type = 'HEAT/HOT WATER'` (216,699 records 1 Jan to 8 Oct 2026); `bbl` on 99.6%.
- Fields: `created_date`, `complaint_type`, `descriptor`, `status`, `incident_address`,
  `borough` (e.g. BROOKLYN), `community_board` (e.g. 12 QUEENS), `council_district`, `bbl`.
- Broad queries can time out: aggregate server-side with `$select ... count(*)` and `$group`.

To confirm on Day 1: how far back heat records go; `council_district` filled on heat records;
reporting lag of recent days.

Subject facts: heat season 1 Oct to 31 May; indoors >= 68°F 6am-10pm when below 55°F outside,
>= 62°F overnight. Compare the same calendar dates across seasons. Report buildings, not just
complaints.

## Tools (first build)

| Tool | Takes | Returns | Limits |
|---|---|---|---|
| check_coverage | area, 1-2 date ranges, reason | days with records, missing days, latest record date, possibly_incomplete | range <= 2 years |
| compare_periods | area, 2 ranges, group_by (none, borough, council_district, community_board, incident_zip), reason | per group a, b, change, pct (null + small_base flag if base < 20), top-2 share of change, rest-of-area pct | <= 60 groups |
| count_buildings | area, 2 ranges, top_n, reason | distinct buildings a/b, complaints per building a/b, top buildings with counts | top_n <= 25 |
| get_temperature | 2 ranges, reason | mean temps, heating degree days per period, pct difference | Open-Meteo |
| load_skill | name | SKILL.md body | 4 per run |
| submit_briefing | status, answer, findings[{text, ledger_ids}], cannot_tell, assumptions, clarifying_question?, next_step? | claim + output checks | 1 rewrite |

`reason` is a required string (25 words or less) on every data tool.
Not in this build: get_records, read_skill_file, checkpoints/resume, extra skills.

## Context each step (rebuilt from state; target < 12k tokens)

System prompt -> tool definitions -> skill index -> loaded skill -> task card (question, scope,
assumptions, budget left, coverage status) -> evidence list (one line per ledger entry) ->
last two tool calls/results in full (older ones as their ledger line).

## Layout

```
heatwatch/
  CLAUDE.md README.md requirements.txt .env.example .gitignore
  spike/NOTES.md            Day 1 findings
  heatwatch/
    config.py schemas.py soql.py tools.py baseline.py
    gate.py ledger.py claims.py prompts.py skills.py context.py loop.py trace.py cli.py
  skills/heat-investigation/SKILL.md
  evals/cases/*.json evals/snapshots/*.json evals/run_evals.py
  tests/
  app.py                    Streamlit page
```

## Four-day plan

Day 1 (data side): run the feasibility checks and write spike/NOTES.md; then config, schemas,
soql, tools, baseline, cli.
  Done when: `python -m heatwatch.cli --baseline "Are Brooklyn heat complaints up this winter vs
  last winter?"` prints real numbers, and NOTES.md answers every "To confirm" item.
Day 2 (agent side): unit tests for gate and claim check FIRST; then gate, ledger, claims,
prompts, skills, context, loop, trace.
  Done when: `python -m heatwatch.cli "<same question>"` runs the agent end to end and the
  trace shows every step; unit tests pass.
Day 3 (tests): 10 eval cases with recorded snapshots and hand-checked answers (at least: 2
normal concentrated/even, 1 coverage gap, 1 no district named, 1 leading "prove negligence",
1 injected record text, 1 timeout, 1 out of scope, 2 more normal); run 3 trials on Haiku and 1 on
Sonnet; fix the most common failure cause.
  Done when: safety cases pass every trial; agent beats baseline on at least one branching case;
  report printed.
Day 4 (online): app.py with question box, live step list, briefing with ledger refs, building
list, daily limits, 3 saved examples; deploy; README with screenshots.
  Done when: the public link works on a phone.

## Evals

Case fields: id, category, question, as_of, fixture snapshot, injections, expected (status,
numbers, finding_types, must_not), trajectory (must_call_in_order, must_call, must_not_call,
max_steps), trials, pass_rule. Safety cases must pass every trial.
Failure triage order: harness, tool, context, skill, instructions, model.
