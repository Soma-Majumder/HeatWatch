# Prompts to paste into Claude Code, one day at a time

Start each day in a fresh Claude Code session inside the heatwatch folder.
After each day: check the "done when", then commit with git.

## Day 1: data side

Read CLAUDE.md. Do Day 1 only.
First, run the feasibility checks and write spike/NOTES.md: how far back HEAT/HOT WATER records go,
whether council_district is filled in on heat records, how many recent days look incomplete, and a
test call to Open-Meteo for Central Park daily means for Oct 1-Jan 15 of two seasons. Then run three
real questions by hand and note which follow-up step each one needs.
Then build config.py, schemas.py, soql.py, tools.py (check_coverage, compare_periods,
count_buildings, get_temperature), baseline.py and cli.py.
Stop when the Day 1 "done when" passes, and show me the output.

## Day 2: agent side

Read CLAUDE.md. Do Day 2 only.
Write unit tests for the gate and the claim check first, from the hard rules. Then build gate.py,
ledger.py, claims.py, prompts.py, skills.py, context.py, loop.py and trace.py, and wire the agent
into cli.py.
Run the Brooklyn question end to end. Show me the trace, the token count and the cost of the run.
Stop there.

## Day 3: tests

Read CLAUDE.md. Do Day 3 only.
Create the 10 eval cases listed in CLAUDE.md with recorded snapshots. Show me each expected answer
and how you computed it so I can check it. Then write evals/run_evals.py, run the baseline, run the
agent 3 trials per case on Haiku and 1 on Sonnet, and print a report side by side.

Then, for failures:
List every failing case, open its trace, and tag the cause (harness, tool, context, skill,
instructions, model) in that order. Propose ONE fix for the most common cause. Do not apply it
until I say yes.

## Day 4: online

Read CLAUDE.md. Do Day 4 only.
Build app.py in Streamlit: a question box, a live list of steps as they happen, the briefing with
ledger references, the building list in a fold-out, the daily limits, and 3 saved example answers
that show without calling the API. Read the API key from Streamlit secrets when deployed and .env
locally. Then tell me exactly how to deploy on Streamlit Community Cloud and set the secret, and
update README.md with screenshots.

## Useful anytime

- "Explain <file> to me line by line, as if I know only basic Python."
- "Stop. We are only on Day N."
- "What did this run cost, and which step used the most tokens?"
- "Show me the trace for the last run as a readable list."
