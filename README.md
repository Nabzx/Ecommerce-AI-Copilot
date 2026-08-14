# StoreSense

An AI dashboard for **noszn**, a small clothing brand on Shopify. Built so the
owner can open one page and see how the shop is doing, ask it questions in
plain English, and find out a size is going before it goes.

> **Demo video:** _coming soon_
> **Live:** _coming soon_

![StoreSense](docs/screenshot.png)

---

## What it does

**The numbers.** Revenue, average order value, units, repeat-purchase rate,
best sellers, and what's running low — each against the previous period.

**A copilot that cites its sources.** Ask "what's our returns policy?" and it
answers from the shop's own documents with a reference to the one it used. Ask
"how did we do this week?" and it answers from the live figures. Answers stream
in, and you can ask by voice.

**Stockout forecasting.** A model predicts how many days each size has left.
The card shows how accurate it actually is, measured against a moving average.

**Semantic search.** "cozy autumn pieces" finds the beanie and the crewneck
without either word being anywhere in the catalogue.

**Alerts in plain English.** Type "warn me when a hoodie has less than two
weeks of stock left" and it becomes a rule the dashboard checks from then on.
It shows you how it read you, so you can tell it understood.

**Copy in noszn's voice.** Product descriptions and win-back emails, lowercase
and understated, with a banned-words list to keep the model off "elevate your
wardrobe".

**Photo tagging.** Upload a product shot, get back tags from the vocabulary the
shop already uses.

**A Monday morning brief.** A short summary of the week and what needs doing,
readable on the dashboard and emailed on a schedule by an AWS Lambda. The one part that comes
to you rather than waiting to be opened.

**Review sentiment.** Classifies reviews and surfaces what people keep
mentioning — for noszn, the complaints are mostly about sizing.

---

## Running it

Needs Python 3.12+ and Node 20+. Works with **no credentials and no paid keys**.

```bash
make demo      # installs everything and fills the database with a year of data
make api       # in one terminal
make web       # in another
```

Then open **http://localhost:3000**.

The dashboard works straight away. For the AI features you need a model —
[Ollama](https://ollama.com) is free and runs locally:

```bash
ollama pull llama3.1 && ollama pull nomic-embed-text
```

Use an 8B or bigger. Smaller models read the right figure out of the context
and then invent a comparison to wrap around it.

Optional extras: `ollama pull moondream` for photo tagging, and
`pip install -r api/requirements-voice.txt` for voice.

<details>
<summary>Docker instead</summary>

```bash
docker compose run --rm seed
docker compose up --build
```
</details>

<details>
<summary>Pointing it at a real Shopify store</summary>

In Shopify: **Settings → Apps → Develop apps → Create an app**, then give it
these Admin API scopes and install it to get the token.

| Scope | For |
|---|---|
| `read_products` | the catalogue, sizes and stock levels |
| `read_orders` | revenue, AOV, units, the forecast |
| `read_customers` | repeat-purchase rate |
| `read_inventory` | cost per item, which is what makes margin real |

`read_orders` only covers the last 60 days by default. Anything older needs
**read_all_orders**, which Shopify grants on request — without it the forecast
has two months of history to learn from instead of a year.

Copy `api/.env.example` to `api/.env`, fill in `SHOPIFY_STORE_DOMAIN` and
`SHOPIFY_ACCESS_TOKEN`, then:

```bash
cd api && python -m app.shopify --check   # credentials first
cd api && python -m app.shopify && python -m app.rag
```

Or press **Connect store** in the dashboard header, which does the same thing.
The header shows whether you're looking at demo data or the real shop.

Two things don't come across. **Reviews** — Shopify has no reviews API, they
live in whatever review app the shop uses, so the sentiment card needs them
imported separately. And the **policy documents** in `api/app/knowledge/` are
written by hand, not synced, so they need replacing with the shop's real
shipping, returns and sizing pages before the copilot cites them at anyone.

Archived products still come down, because their past orders are part of the
revenue, but they're kept out of the stock reports and search — a discontinued
line isn't a buying decision.

Customer names and emails are anonymised on the way in and never stored as
they arrive.
</details>

---

## What this demonstrates

- **A production API wrapper** — one gateway for every model call, with
  timeouts, retries that know a 500 is worth repeating and a 400 isn't, and
  rate limiting. Provider-agnostic, so it runs on Ollama or OpenAI unchanged.
- **Cited RAG** — chunking, embeddings, a vector store, and answers that point
  at the document they came from.
- **A streaming copilot** — SSE, typing state, and failures that arrive as
  events, because once a stream has started an HTTP status can't reach the
  browser.
- **Forecasting that was measured, not assumed** — the first version lost to a
  28-day moving average. See below.
- **Multimodal tagging** — a vision model looks, a text model structures.
- **Voice** — Whisper locally, feeding the same chat path as typing.
- **Semantic search** over the catalogue.
- **Sentiment with a closed theme vocabulary**, so the counts actually add up.
- **Scheduled delivery on AWS** — EventBridge and a dependency-free Lambda, so
  the app itself needs no scheduler.
- **Token and cost tracking** on every model call, broken down by feature.
- **Tests and CI** on the gateway, retrieval, login and the Lambda, none of
  which touch a model.
- **A shared-password login** — off by default so a fresh clone just runs, on
  the moment you set `APP_PASSWORD`. Signed tokens, constant-time comparison,
  and a much tighter rate limit on the one endpoint where requests are guesses.

### On the forecast

It predicts how many units each size sells over the next 28 days, then turns
that into days of stock left.

The honest version of the story: predicting one day at a time and feeding each
guess back in scored **41% off** against a moving average's **33%**. Fixing
that got it to a tie, not a win — because a size selling fifteen units a month
carries about 26% Poisson noise no matter what you do, and the measured floor
across this catalogue is **32.6%**. Both were sitting on it.

Model and baseline get different things wrong though, so the shipped forecast
is half of each: **36.9%** against the baseline's **39.7%** over four rolling
windows. The dashboard shows that comparison under the card.

```bash
cd api && python -m app.forecast   # retrains and prints the backtest
```

---

## How it fits together

```
  Shopify Admin API ─┐
                     ├──► SQLite (or Postgres) ──► FastAPI ──► Next.js dashboard
  Synthetic seeder ──┘                              │
                                                    ├── llm.py    one gateway
                                                    ├── rag.py    retrieval + citations
                                                    └── forecast.py
```

`api/` is the backend and every model call goes through `api/app/llm.py`.
`web/` is the dashboard. The copilot is docked on the right, or a sheet you
pull up on a phone.

## Tests

```bash
make test
```

Covers the gateway's retry and error handling, and chunking and retrieval.
Neither needs a model running.

## Data

The seeder is fake, deliberately. It simulates a year day by day — quiet
Mondays, busy weekends, hoodies picking up in autumn, stock draining between
restocks — so the patterns are real enough for the forecaster to find. No real
customer data is in this repo, and the Shopify sync anonymises what it pulls.

## Licence

MIT.
