# HeatWatch Technical Choices Explained

Oct 14, 2026 · Dikshyant

**Recommendation:** build HeatWatch in Python and run it on **Claude Haiku 4.5**, the cheapest current Claude model. Run the test suite once on a larger Claude model to see whether it does better. Put it online as a Streamlit app with a daily question limit, so a public link cannot run up your bill. It uses one AI model, no model training, and no extra machine learning, because the numbers come from database queries and plain arithmetic.

What you told me, and what it changed:

| You said | What it changes |
| --- | --- |
| A portfolio piece, online | It needs a public link, simple hosting, and protection against strangers spending your money |
| AI budget: not sure yet | Start on the cheapest model that can do the job. Section 6 gives cost estimates so you can set a limit |
| Some Python | Python everywhere. Claude Code writes most of the code; you two read, run and adjust it |
| Working in 3–4 days | The plan shrinks from about 10 days to 4: fewer tests, no crash recovery, and a ready-made web framework instead of a hand-built page |

## 1. The big picture

HeatWatch is one Python app. A visitor types a question, the agent loop asks Claude for one step at a time, and the tools fetch numbers from two public data sites. You write the code on your laptops with Claude Code and push it to GitHub, and the free host runs it from there.

```
Visitor (browser)
   │ asks
   ▼
┌─────────────── Streamlit Community Cloud (free hosting) ───────────────┐
│  Streamlit page · app.py   (question box, daily limit, live steps)     │
│        │                                                               │
│        ▼                                                               │
│  Agent loop  (loop · gate · claim check · 4 data tools · ledger) ◄──►  Claude API (Haiku 4.5, one step)
│        │                                         ── read only ──►  NYC Open Data (311 complaints)
│        ▼                                         ── read only ──►  Open-Meteo (daily temperatures)
│  SQLite + trace files  (evidence, cache, step logs)                    │
└────────────────────────────────────────────────────────────────────────┘
        ▲ deploys
GitHub repo (code, never the key)  ◄── push ──  Your laptops (built with Claude Code)
```

Only Claude is AI. Everything inside the hosting box is your code; the data sites are public and HeatWatch only reads them.

## 2. Which Claude model, and why

Start with **Claude Haiku 4.5**. HeatWatch asks the model to make about nine small, well-defined choices per question, and the code double-checks every one. That task rewards speed, low cost and reliable tool calling more than deep reasoning.

The model never sees the raw data and never does arithmetic. On each step it reads a short summary and picks one tool, or writes the final briefing.

| Model | API id | Price per million tokens (input / output) | Fit for HeatWatch |
| --- | --- | --- | --- |
| **Haiku 4.5** (recommended start) | `claude-haiku-4-5-20251001` | $1 / $5 | Fastest and cheapest; Anthropic describes it as near-frontier intelligence |
| Sonnet 5.5 | `claude-sonnet-5-5` | needs checking | The comparison run: smarter, several times the cost |
| Opus 5.5 | `claude-opus-5-5` | needs checking | More capability than nine small choices need |
| Fable 5.1 | `claude-fable-5-1` | needs checking | The top tier, built for much harder problems; wasted here |

Confirm current ids and prices in the Anthropic Console before you set `.env`. Pin a specific model id, not an alias.

**Why Haiku first:** cost (a public link means strangers can ask on your bill), speed (about nine calls must fit in 45 seconds), a safety net in code (wrong numbers and blame claims are caught by code), and evidence (the tests tell you whether Haiku is enough).

**When to switch to Sonnet 5.5:** if Haiku fails 2 or more of the 10 test cases on choosing the right path, and one prompt fix does not solve it. Switching is one line in `.env`.

**What you give up:** Haiku may word briefings less smoothly and may need clearer skill instructions.

## 3. Tech stack, and why each piece

| Piece | Pick | Why this one | What you give up |
| --- | --- | --- | --- |
| Language | Python 3.12 | You know some; best tools for data; Claude Code writes it well | Nothing |
| Talking to Claude | `anthropic` Python SDK | Anthropic's own library | Nothing; a framework would hide the loop you are learning |
| Calling the data sites | `httpx` | Timeouts built in | Nothing |
| Checking tool inputs | `pydantic` | One class per tool produces the schema sent to Claude and validates what comes back | A small library to learn |
| Complaint data | NYC Open Data (Socrata) API with SoQL | Free, public, counts on its server | Large queries can time out |
| Weather data | Open-Meteo historical API | No key for non-commercial use; daily data back to 1940 | Not NOAA's official station record |
| Storage | SQLite | Ledger and cache in one file | Resets when the hosted app restarts |
| Web page | **Streamlit** | Python-only web page | Less design control; replaces the earlier FastAPI + HTML plan |
| Hosting | Streamlit Community Cloud | Free; deploys from GitHub | Free-tier limits need checking |
| Tests | `pytest` | Standard | Nothing |
| Secrets | `.env` locally; host secrets when deployed | Key never in code or GitHub | Nothing |
| Version control | Git and GitHub | Required by the host | Nothing |
| Building it | Claude Code | Writes most of the code from CLAUDE.md | Not part of HeatWatch itself |

Deliberately not used: agent frameworks, Docker or a cloud server, a database server, a separate front-end framework.

## 4. The modules to build, and in what order

| File | What it does | Approx. lines | Day |
| --- | --- | --- | --- |
| `config.py` | Settings from `.env` | 30 | 1 |
| `schemas.py` | One pydantic class per tool | 80 | 1 |
| `soql.py` | Builds queries from checked inputs | 80 | 1 |
| `tools.py` | Coverage, compare, buildings, temperature | 200 | 1 |
| `baseline.py` | Fixed pipeline with no AI choices | 60 | 1 |
| `gate.py` | Checks each tool call before it runs | 80 | 2 |
| `ledger.py` | Saves every result with an id; caches | 60 | 2 |
| `claims.py` | Checks the final briefing | 120 | 2 |
| `prompts.py` | The system prompt | 60 | 2 |
| `skills.py` + SKILL.md | Loads the investigation method | 40 | 2 |
| `context.py` | Builds what the model sees each step | 70 | 2 |
| `loop.py` | The agent loop with budgets | 120 | 2 |
| `trace.py` | Step log | 30 | 2 |
| `cli.py` | Terminal entry point | 20 | 2 |
| `evals/` | 10 cases, recorded data, grader | 150 | 3 |
| `app.py` | Streamlit page with daily limit | 100 | 4 |
| `tests/` | Unit tests for gate, claims, budgets | 120 | 2–3 |

1. **Day 1, data side.** Feasibility checks, then config, schemas, soql, tools, baseline. Done when the baseline answers the Brooklyn question with real numbers.
2. **Day 2, agent side.** Tests for gate and claim check first, then the agent. Done when the agent answers end to end with a full trace.
3. **Day 3, tests.** 10 cases, 3 trials on Haiku, 1 on Sonnet; fix the top failure. Done when safety cases pass every trial and the agent beats the baseline on a branching case.
4. **Day 4, online.** Streamlit page, limits, deploy, README. Done when the link works on a phone.

Cut to fit four days: crash recovery, `get_records`, `read_skill_file`, the second and third skills, and the larger test suite.

## 5. Other AI and ML

HeatWatch uses exactly one AI model, Claude, and trains nothing.

| Technique | Used? | Why |
| --- | --- | --- |
| Large language model (Claude) | Yes | Understands the question, picks the next analysis, writes the briefing |
| Training or fine-tuning a model | No | No labeled examples, costly, not needed |
| Embeddings and a vector database | No | The data is a table queried exactly |
| Forecasting model | No | Out of scope; invites overclaiming |
| Text classifier | No | 311 already labels complaint types |
| Simple statistics in code | Yes | Percent change, share of change, complaints per building, heating demand |

Heating degree days: HDD = sum over days of max(0, 65 − daily mean °F).

Possible upgrades later: a weather-adjusted baseline (a simple regression of complaints on heating degree days), and z-score anomaly flags. Both would be new data tools returning numbers.

## 6. Cost and speed

About 9 model calls, about 70,000 input and 2,700 output tokens per question.

| Model | Per question | Per 100 questions |
| --- | --- | --- |
| Haiku 4.5 ($1 / $5 per million) | about $0.08 | about $8 |
| Sonnet 5.5 (if $3 / $15; needs checking) | about $0.25 | about $25 |

Budget: about $15 to build and test; a $10–20 monthly spend limit for the demo, plus app limits of 20 questions a day and 3 per visitor. Prompt caching and saved example answers can cut cost later. Expected speed: roughly 20–40 seconds per question; measure on Day 2.

## 7. Glossary

| Term | Plain meaning |
| --- | --- |
| Agent | A program where an AI model chooses its next step from what it just learned |
| Agent loop (harness) | Code that asks the model for a step, checks it, runs it and records the result |
| API / API key | A way for programs to talk over the internet / its secret password, tied to your bill |
| Baseline | A version with no AI choices, for comparison |
| Claim check | Code that verifies every number in the answer against saved results |
| Eval | A test question with known right answer and steps |
| Evidence ledger | A numbered log of every result the agent got |
| Heating degree days | How much colder than 65°F the days were, added up |
| Prompt caching | Reusing an unchanged request start so it costs less |
| SoQL / Socrata | The query language and platform behind NYC Open Data |
| System prompt | Standing instructions sent to the model on every call |
| Token | Roughly three-quarters of a word; you pay per token |
| Tool calling | The model asking your code to run a named function |
| Trace | A step-by-step log of one run |

## 8. Decisions

| Decision | Recommendation |
| --- | --- |
| Default model | Haiku 4.5, one Sonnet 5.5 comparison on Day 3 |
| Web page | Streamlit |
| Weather source | Open-Meteo |
| Monthly spend limit | $10–20, set in the Anthropic Console |
| GitHub repo | Public; `.env` ignored from the first commit |
| Demo limits | 20 a day, 3 per visitor, 3 saved examples |

## Sources

- Anthropic models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Open-Meteo historical weather API: https://open-meteo.com/en/docs/historical-weather-api
- Streamlit Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud
- NYC 311 Service Requests: https://data.cityofnewyork.us/resource/erm2-nwe9.json
