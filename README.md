# HeatWatch

An AI research agent that answers questions about New York City heat and hot water complaints,
using public 311 data. It picks each next analysis from what the last result showed, and every
number in its answer links back to the query that produced it.

Built by Dikshyant and Soma.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your Anthropic API key to .env
python -m heatwatch.cli "Are Brooklyn heat complaints up this winter compared to last winter?"
streamlit run app.py
```

## How it works

- `heatwatch/loop.py` asks Claude for one step at a time.
- `heatwatch/gate.py` checks every tool call before it runs.
- `heatwatch/tools.py` queries NYC Open Data and Open-Meteo, and computes every number.
- `heatwatch/claims.py` removes any claim the evidence does not support.

Data: NYC 311 Service Requests (NYC Open Data); weather: Open-Meteo historical API.
