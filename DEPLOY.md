# Deploying

Three pieces: the dashboard on Vercel, the API somewhere that can run a
container, and a hosted Postgres.

Vercel can't host the API — FastAPI here holds a trained model in memory and
streams responses, neither of which fits serverless functions well. Render's
free tier is the least trouble.

---

## 1. Database — Neon

Make a project at [neon.tech](https://neon.tech) and copy the connection
string. It'll look like `postgresql://user:pass@host/db`.

The code rewrites `postgres://` and picks the psycopg 3 driver itself, so
paste whatever Neon gives you.

## 2. API — Render

New → Web Service, point it at this repo, root directory `api`, and let it use
the Dockerfile.

Environment:

```
DATABASE_URL      = the Neon string
LLM_BASE_URL      = https://api.openai.com/v1     (or another provider)
LLM_API_KEY       = your key
LLM_MODEL         = gpt-4o-mini                   (or similar)
LLM_EMBED_MODEL   = text-embedding-3-small
```

Ollama is a local tool — nothing on the internet can reach the one on your
laptop, so a deployed instance needs a hosted provider. The gateway speaks the
same API either way, so nothing in the code changes.

Once it's up, seed it from the Render shell:

```bash
python -m app.seed && python -m app.rag
```

## 3. Dashboard — Vercel

Import the repo, set **Root Directory** to `web`, and add:

```
NEXT_PUBLIC_API_URL = https://your-api.onrender.com
```

It has to be set before the build, not after — Next bakes `NEXT_PUBLIC_*` into
the bundle at build time, so changing it later means redeploying.

## 4. Let the API accept the dashboard

`api/app/main.py` allows localhost by default. Add the Vercel domain:

```python
allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
```

---

## Costs

Neon and Vercel have free tiers that comfortably fit this. Render's free web
services sleep after inactivity, so the first request after a quiet spell takes
about thirty seconds to wake up.

The LLM is the only thing that really costs anything, and only if you use a
paid provider. Locally with Ollama it's free.
