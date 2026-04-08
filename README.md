
# FreeMAD — Multi-Agent Debate Chat App

A conversational AI web application where multiple agents debate your question using the
**FreeMAD protocol** and return the highest-scoring answer. Built with
**Google ADK**, **Django (ASGI)**, and **React**, served in a single Docker container.

---

## Project Structure

```
freemad-app/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/
│   │   ├── settings.py       ← Django settings
│   │   ├── urls.py           ← URL routing
│   │   └── asgi.py           ← ASGI entry point for Uvicorn
│   └── chat/
│       ├── views.py          ← SSE streaming endpoint + React catch-all
│       ├── urls.py
│       └── freemad/
│           └── agent.py      ← FreeMAD protocol (async generator)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js        ← Vite build + dev proxy config
│   └── src/
│       ├── main.jsx
│       ├── App.jsx           ← Chat UI with SSE streaming
│       └── index.css
├── Dockerfile                ← Multi-stage build (Node → Python)
├── docker-compose.yml        ← Local dev (hot reload for both services)
├── render.yaml               ← One-click Render deployment
├── .env.example              ← Copy to .env and fill in your keys
└── .gitignore
```

---

## How It Works

```
Browser  ──POST /api/chat/──▶  Django view (chat/views.py)
                                     │
                              AsyncGenerator SSE stream
                                     │
                           chat/freemad/agent.py
                                     │
                    N agents × R rounds of debate
                    (google-adk + your chosen LLM)
                                     │
                    Scores responses by semantic similarity
                                     │
                    Yields progress events + final answer
                                     │
Browser  ◀── SSE stream ─────  Django StreamingHttpResponse
(React reads stream live and updates the UI in real time)
```

---

## Quick Start — Local Development

### Prerequisites
- Docker + Docker Compose installed (you already have this ✅)
- An API key for your chosen model provider

### Step 1 — Clone and configure

```bash
# Copy the example env file
cp .env.example .env

# Open .env and fill in your API key and model settings
nano .env   # or use any text editor
```

The minimum you need to set in `.env`:

```env
MODEL_PROVIDER=google          # or openai, ollama, huggingface
GEN_MODEL_NAME=gemini-2.0-flash
GOOGLE_API_KEY=your-key-here   # or API_KEY= for openai/huggingface
DJANGO_SECRET_KEY=any-long-random-string
```

### Step 2 — Place your agent file

Copy your original `agent.py` and the new `agent.py` from this project into:
```
backend/chat/freemad/agent.py
```
The refactored `agent.py` in this repo is a drop-in replacement — it has the
same logic but is now a callable async generator Django can use.

### Step 3 — Start with Docker Compose (recommended for development)

```bash
docker compose up
```

This starts two services:
- **Backend** (Django + Uvicorn) at http://localhost:8000 — hot-reloads on Python changes
- **Frontend** (Vite) at http://localhost:5173 — hot-reloads on React changes

Open **http://localhost:5173** in your browser. The Vite dev server proxies
`/api/*` requests to Django automatically.

### Step 4 — Or build the production container

```bash
# Build the single all-in-one image
docker build -t freemad .

# Run it (loads your .env file)
docker run -p 8000:8000 --env-file .env freemad
```

Open **http://localhost:8000** — Django serves both the React app and the API.

---

## Switching Model Providers

Change `MODEL_PROVIDER` in `.env` — no code changes needed.

| Provider | MODEL_PROVIDER | Required .env vars |
|---|---|---|
| Google Gemini | `google` | `GOOGLE_API_KEY`, `GEN_MODEL_NAME=gemini-2.0-flash` |
| OpenAI | `openai` | `API_KEY=sk-...`, `GEN_MODEL_NAME=gpt-4o` |
| Ollama (local) | `ollama` | `API_BASE=http://localhost:11434`, `GEN_MODEL_NAME=llama3` |
| HuggingFace | `huggingface` | `API_KEY=hf_...`, `GEN_MODEL_NAME=meta-llama/Llama-3-8B-Instruct` |

---

## Deploying to Render (Free)

1. Push this project to a GitHub repository
2. Go to https://dashboard.render.com → **New** → **Web Service**
3. Connect your GitHub repo
4. Render detects `render.yaml` automatically and pre-fills the config
5. Go to **Environment Variables** in the Render dashboard and set:
   - `GOOGLE_API_KEY` (or your chosen provider's key)
   - `MODEL_PROVIDER`
   - `GEN_MODEL_NAME`
6. Click **Deploy**

Render builds the Docker image and gives you a public URL like
`https://freemad-app.onrender.com`.

> **Note:** Render's free tier spins down after 15 minutes of inactivity.
> The first request after spin-down takes ~30 seconds. This is normal.

---

## API Reference

### `POST /api/chat/`

**Request body:**
```json
{
  "message": "Your question here",
  "guiding_prompt": "Optional meta-instruction for agents"
}
```

**Response:** `text/event-stream` (SSE)

Each event is a JSON object on a `data:` line:

```
data: {"type": "progress", "message": "Round 1 of 2 — agents are debating…"}

data: {"type": "agent", "round": 1, "agent": "debater_1", "text": "…"}

data: {"type": "final", "message": "The winning response text…"}

data: [DONE]
```

---

## Common Issues

**`permission denied` running docker** — run `newgrp docker` or log out and back in.

**`No module named 'google.adk'`** — make sure you ran `pip install -r requirements.txt` or rebuilt the Docker image.

**Agent returns `None`** — your API key may be missing or invalid. Check `.env`.

**Render build fails on torch/sentence-transformers** — these are large packages.
Render free tier has a 512 MB RAM limit. If the build runs out of memory, set
`N_AGENTS=2` and `R_ROUNDS=1` in Render's environment variables to reduce load.

**Ollama inside Docker** — if using Ollama, it must be reachable from inside the
container. On Linux, use `http://host.docker.internal:11434` as `API_BASE`.