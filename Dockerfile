# ══════════════════════════════════════════════════════════════════════════════
# Dockerfile — FreeMAD (React + Django in a single container)
#
# Build strategy: two-stage build
#
#   Stage 1 — "frontend-build"  (Node.js)
#   ───────────────────────────────────────
#   Install npm dependencies and run `vite build`.
#   Outputs a static bundle to /frontend/dist/
#
#   Stage 2 — "app"  (Python / Django)
#   ───────────────────────────────────────
#   Install Python dependencies.
#   Copy the React build from Stage 1 into backend/frontend_build/
#   WhiteNoise serves those static files directly from Django.
#   Uvicorn starts the ASGI server.
#
# The final image contains ONLY the Python layer — the Node.js layer
# is discarded, keeping the image lean.
# ══════════════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Build the React frontend
# ──────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Copy dependency manifests first — Docker caches this layer separately.
# The expensive `npm install` only re-runs when package.json changes.
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend source and build
COPY frontend/ ./
RUN npm run build
# Output is now in /frontend/dist/


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Django application
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS app

# Prevent Python from writing .pyc files and buffering stdout/stderr.
# Unbuffered output means logs appear immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────
# gcc and build-essential are needed to compile some Python packages
# (e.g. torch, sentence-transformers C extensions).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────
# Copy requirements first for layer caching — only re-installs when
# requirements.txt changes, not on every code change.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────
COPY backend/ .

# ── React build ───────────────────────────────────────────────────────────
# Copy the Vite output from Stage 1 into the directory that
# settings.py points WHITENOISE_ROOT and FRONTEND_BUILD_DIR at.
COPY --from=frontend-build /frontend/dist ./frontend_build/

# ── Static files ──────────────────────────────────────────────────────────
# collectstatic is required by Django even though WhiteNoise serves
# files from frontend_build/ directly. It's a one-time setup step.
RUN python manage.py collectstatic --noinput

# ── Runtime ───────────────────────────────────────────────────────────────
# Expose the port Uvicorn will listen on.
EXPOSE 8000

# Start Uvicorn pointing at the ASGI application object in config/asgi.py.
# --workers 1 is fine for a school project; increase for production load.
CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
