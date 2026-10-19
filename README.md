# 🔥 HeatWatch

**An AI helper that sorts NYC heat and hot water complaints by how urgent they are.**
A tenant tells it what is wrong, and it gives back a ticket number, a priority, a next step and an honest time estimate. 🎫

> 🧭 **Where we are:** the brain (scoring, duplicates, time estimates), the chat, tickets, replies, Spanish, voice and privacy are built and tested. The reviewer screen, the ticket lookup page and the automatic re-checks are next.

---

## 😟 The problem

When the heat goes out, tenants report it to 311 and then wait. They don't know if anyone saw it, how serious it was rated, or when it will be fixed.

The public record for **Washington Heights and Inwood** (Manhattan Community Board 12) shows:

- 📊 **40,700** heat and hot water complaints in two years, in one neighborhood
- ⏱️ A typical complaint takes about **42 hours** to close, and **1 in 10** takes more than **84 hours**
- 🔁 About **35%** are closed as a duplicate of another report
- 🚪 About **14%** are closed because the city could not get into the apartment
- 🗓️ No complaint has a due date, and nothing says how urgent it is

## 👥 Who is affected

| Who | What they go through |
|---|---|
| 🏠 **Tenants** | Cold apartments in winter, no answer, no ticket they can follow. Families with babies or older people are hit hardest. |
| 👩‍💼 **Reviewers** | A pile of complaints with no ranking. A gas smell or a whole building without heat looks the same as a small issue. |
| 🏘️ **The neighborhood** | The same buildings keep failing. **21 addresses** account for about **19%** of all complaints. |

## 💡 The solution

HeatWatch gives every complaint three things that are missing today:

1. 🚦 **An urgency level** (low, normal, high, critical)
2. 👉 **A clear next step**, with an honest time estimate
3. 🎫 **A ticket number** the tenant can use to check progress

| For... | HeatWatch gives them... |
|---|---|
| 🏠 Tenants | A short, kind chat in **English or Spanish**, a ticket number, a priority and a realistic estimate |
| 👩‍💼 Reviewers | Whole-building outages, gas smells and vulnerable households at the top, so a person looks at them first |
| 🏘️ The neighborhood | Repeat-offender buildings that stand out |

⚠️ **HeatWatch does not file with the city.** It tells tenants clearly to report to 311 too. HPD (the city housing agency) stays the official record.

---

## 🤝 Who did what

We are two builders.

<table>
  <tr>
    <td align="center" width="50%">
      <a href="https://github.com/Soma-Majumder"><img src="docs/team/soma.png" width="120" alt="Soma Majumder" /></a><br />
      <b>Soma Majumder</b><br />
      🎊 Drop by and say hello! Always happy to chat:<br />
      <a href="https://github.com/Soma-Majumder">🐙 GitHub</a> · <a href="https://www.linkedin.com/in/somamajumder/">💼 LinkedIn</a>
    </td>
    <td align="center" width="50%">
      <a href="https://github.com/Diksh-giri"><img src="docs/team/dikshyant.png" width="120" alt="Dikshyant Giri" /></a><br />
      <b>Dikshyant Giri</b><br />
      🎊 Drop by and say hello! Always happy to chat:<br />
      <a href="https://github.com/Diksh-giri">🐙 GitHub</a> · <a href="https://www.linkedin.com/in/dikshyant-giri/">💼 LinkedIn</a>
    </td>
  </tr>
</table>

| | 🧑‍💻 Soma | 🧑‍💻 Dikshyant |
|---|---|---|
| 📝 **Planning** | Product requirements (PRD), build plan, interfaces doc | Early design docs and project setup, first look at the data |
| 🧠 **Triage engine** | Address cleaner, priors, scoring and overrides, duplicates, time estimates, backtest | |
| 📥 **Data** | Data loader, daily refresh job | Day 1 data exploration |
| 🎫 **Tickets and replies** | Ticket store, reply templates, output gate | |
| 💬 **Intake chat** | The chat agent: warm tone, asks for hours, politely declines off-topic questions | |
| 🛡️ **Safety layer** | Architecture diagram and the plain-English security doc | **Led:** input guard hardened and proven with tests |
| 🌎 **Spanish** | | **Led:** Spanish replies and Spanish intake |
| 🔊 **Voice** | The `--speak` option (English and Spanish) | |
| 🔒 **Privacy** | 90-day deletion and deletion requests | |
| ✔️ **Quality** | Automatic tests on every pull request, README | Tests for the input guard and Spanish |

Together: **33 pull requests** and **135 automated tests**, all passing. ✅

---

## ✅ What we finished

| | Piece | In plain words |
|---|---|---|
| 🧠 | **Triage engine** | Scores urgency, spots duplicates, and estimates time to fix using 40,690 past complaints |
| 💬 | **Intake chat** | A warm chat that collects the address, building or apartment, heat or hot water, and how long |
| 🛡️ | **Safety layer** | An input guard and an output gate that block tricks, false promises and false "we filed it" claims |
| 🎫 | **Tickets** | Hard-to-guess ticket numbers and a full log of everything that happens to each complaint |
| 🌎 | **Spanish** | Spanish replies and a Spanish intake chat |
| 🔊 | **Voice** | An option to read replies out loud (macOS) |
| 🔒 | **Privacy** | Tenant data is deleted automatically after **90 days**, and no addresses go in logs |
| 📥 | **Data pipeline** | Pulls two years of 311 data, refreshes daily, rebuilds the stats |
| 🔬 | **Backtest** | Replays the scoring on past complaints to see how the bands behave |
| ✔️ | **Automatic tests** | 135 tests run on every pull request |

### 🧱 The pieces, file by file

| Piece | What it does | Where |
|---|---|---|
| 📥 **Data loader** | Pulls two years of complaints from NYC Open Data into a local database | `app/loader.py` |
| 🗄️ **Database layout** | Tables for tickets, events, escalations, address history and priors | `app/schema.sql` |
| 🏠 **Address cleaner** | Makes "516 W 156th St." and "516 WEST 156 STREET" match | `app/address.py` |
| 📈 **Priors and address stats** | Typical close times, duplicate rates, and which addresses keep coming back (21 so far) | `app/priors.py` |
| ⚖️ **Scoring and overrides** | Turns a complaint into a priority with the reasons listed | `app/triage.py` |
| 👯 **Duplicate check** | Spots an open complaint already filed at the same address | `app/duplicates.py` |
| ⏳ **ETA lookup** | Quotes "usually resolved in about X hours, 9 in 10 within Y" | `app/eta.py` |
| 🧩 **One-call engine** | Complaint in; priority, reasons, duplicate, ETA and escalation out | `app/engine.py` |
| 🎫 **Ticket store** | Hard-to-guess numbers, a log of every step, and a safe public view | `app/tickets.py` |
| 💌 **Replies and output gate** | Fixed templates (English and Spanish) that block promises and filing claims | `app/replies.py` |
| 💬 **Intake agent** | The model only asks and extracts; code checks every field and creates the ticket | `app/intake/` |
| 🔒 **Retention** | Deletes tenant data after 90 days | `app/retention.py` |
| 🔬 **Backtest** | Replays the scoring over past complaints | `app/backtest.py` |

---

## 🔁 The loop

HeatWatch works in a loop. Each stage feeds the next, and the last one feeds back into the first.

| Step | What happens | Status |
|---|---|---|
| 👀 **Observe** | Chat with the tenant and look up the address history | ✅ built (needs a model key to run live) |
| 🧠 **Decide** | Score urgency and check for duplicates | ✅ built |
| 📣 **Act** | Reply with a ticket number, next step and time estimate | ✅ built |
| 📝 **Feedback** | Save every step; the tenant checks progress by ticket number | 🟡 saving works, lookup page not yet |
| 🔄 **Loopback** | Re-check tickets that are late, repeated or reopened, and compare our estimates with what really happened | 🟡 started: the daily data refresh keeps our time estimates current; late-ticket re-checks are not built yet |

## 🧰 The harness: "The AI talks. Plain code decides."

The **harness** is the ordinary, checkable code that wraps the AI model. Think of it as guard rails. The model is useful for talking to people, but we don't trust it with decisions that matter.

| Who | Job |
|---|---|
| 🤖 **The AI model** | Asks questions, understands messy tenant text, writes friendly wording |
| ⚙️ **The harness (plain code)** | Checks every field, sets the priority, creates tickets, sends escalations |

The harness has four rules:

1. 🚪 **Input guard.** Tenant text is treated as data, never as instructions. Attempts to trick the AI are blocked.
2. 🔒 **Narrow power.** The AI can't create or change tickets and can't set priority. Only code can.
3. 🚧 **Output gate.** Every reply is checked before a tenant sees it. It can't promise a repair or say we filed anything.
4. 🙋 **Humans for the big claims.** Things nobody can verify ("gas smell", "baby at home") always go to a person.

We also keep the AI to **one job**: turn a heat complaint into a triaged ticket. Anything else gets a kind redirect, never an answer.

### 🏗️ Agent architecture

![Agent architecture diagram](docs/agent-architecture.svg)

The numbered circles (1 to 4) mark where untrusted text could sneak in. The teal boxes are the checks in the way. Plain-English version: [`docs/security-layer.md`](docs/security-layer.md).

---

## 🎯 How a complaint is scored

Every complaint earns points, and the total sets its priority.

![Threshold chart](docs/threshold-chart.svg)

| Priority | Score | What it means |
|---|---|---|
| 🟢 Low | under 3 | Minor, usually outside heat season |
| 🔵 Normal | 3 to 4 | One apartment, heat season, nothing else |
| 🟠 High | 5 to 7 | A whole building out, or a long outage or repeat address |
| 🔴 Critical | 8 or more, or an override | A person looks at it first |

### 🚨 Always critical

1. ☣️ A **safety risk** (for example a gas smell)
2. 👶 A **vulnerable household** with no heat in heat season
3. 🏢 A **whole building** out that is also a repeat-offender address, or has been out **24 hours or more**

### 🧮 Three quick examples

| Situation | Math | Result |
|---|---|---|
| Whole building, heat season, evening | 3 + 2 = 5 | 🟠 High |
| The same, at a repeat-offender address | override fires | 🔴 Critical |
| Apartment, heat season, outage of 30 hours | 1 + 2 + 2 = 5 | 🟠 High |

> ⚠️ **Honest note:** these weights are our best starting guess, not a proven formula. The public data has no field for outage length, vulnerability or safety, so we can't test those yet. We will re-check after the first real tickets.

### 🔍 What the backtest showed

| Priority | Share of complaints | Typical time to close |
|---|---|---|
| 🔴 Critical | about 16% | 34 hours |
| 🟠 High | about 61% | 43 hours |
| 🔵 Normal | about 22% | 47 hours |
| 🟢 Low | about 1% | 39 hours |

The bands show **how bad it is for the tenant**, not how fast the city closes it. Critical cases close sooner partly because many are duplicates. A **repeat-offender address** has 200 or more complaints in two years: 21 addresses, about 19% of complaints, roughly 11 escalations a day.

---

## 🚧 What comes next

- 🖥️ **Reviewer queue:** a ranked screen with escalation alerts, where only reviewers see tenant details
- 💻 **Web chat and ticket lookup:** a page to report and to check a ticket by number
- 🗣️ **Native Spanish review:** a Spanish speaker checks the wording before real tenants see it
- 🔄 **Late-ticket re-checks:** automatic follow-up on tickets that are overdue, repeated or reopened

| Phase | Goal |
|---|---|
| 4️⃣ | Ticket lookup and follow-ups |
| 5️⃣ | Reviewer queue and escalations |
| 6️⃣ | Loopback for late and repeat tickets |
| 7️⃣ | Load and pilot checks |

---

## 🚀 Try it yourself

You need **Python 3.10 or newer**. Nothing else to install.

```bash
# 1. Pull two years of complaints into a local database (about 10 seconds)
python3 -m app.loader

# 2. Build the address stats, then see how the bands behave
python3 -m app.backtest

# 3. Run the tests
python3 -m unittest discover -s tests
```

### 💬 Try the intake chat

```bash
export ANTHROPIC_API_KEY=...   # your own key; never commit it
python3 -m app.intake
```

Add `--speak` to hear each message read aloud (macOS only; Spanish replies use a Spanish voice):

```bash
python3 -m app.intake --speak
```

### 🔄 Keep the data fresh

```bash
python3 -m app.refresh
```

This pulls new complaints, rebuilds the stats, and deletes tenant data older than 90 days. It is safe to run again, and if the city's site is down it leaves your data alone. To run it every morning, add this with `crontab -e` (adjust the folder):

```
0 5 * * * cd /path/to/HeatWatch && /usr/bin/python3 -m app.refresh >> data/refresh.log 2>&1
```

---

## 📁 What's in this repo

```
HeatWatch/
├── app/                 the engine
│   ├── loader.py        pulls 311 data
│   ├── refresh.py       daily job: load, prune, rebuild stats, delete old tenant data
│   ├── retention.py     90-day deletion
│   ├── address.py       cleans addresses
│   ├── priors.py        close-time stats and repeat flags
│   ├── triage.py        scoring and overrides
│   ├── duplicates.py    duplicate detection
│   ├── eta.py           expected timeline
│   ├── engine.py        one call: complaint in, full assessment out
│   ├── tickets.py       ticket store and public view
│   ├── replies.py       reply templates (English and Spanish) and output gate
│   ├── backtest.py      checks the bands against history
│   └── intake/          the chat: guard, prompt, model client, agent, voice
├── tests/               135 tests
├── docs/                diagrams and the security doc
├── BUILD_PLAN.md        phase-by-phase plan
├── INTERFACES.md        contracts between the engine and the agent
└── HeatWatch PRD.docx   product requirements
```

📚 More detail: [`BUILD_PLAN.md`](BUILD_PLAN.md) · [`INTERFACES.md`](INTERFACES.md) · [`docs/security-layer.md`](docs/security-layer.md)

---

## 📌 Good to know

- 🏙️ **Scope:** Washington Heights and Inwood (Community Board 12), heat and hot water only.
- 🏛️ **We don't file with the city.** HeatWatch triages and advises; HPD remains the official record.
- 🏘️ **Public housing (NYCHA)** has its own city process and is out of scope.
- 📡 **Data source:** [NYC Open Data, 311 Service Requests](https://data.cityofnewyork.us/resource/fbiz-gkhq.json)
