"""
config/settings.py — Django project settings for FreeMAD

Key design decisions
────────────────────
• ASGI-only: we use async views + StreamingHttpResponse, which requires
  an ASGI server (Uvicorn). WSGI (gunicorn, mod_wsgi) will not work.

• WhiteNoise: serves the React SPA static files (JS, CSS, assets) directly
  from Django without needing a separate Nginx layer. Simple and Render-friendly.

• CORS: django-cors-headers allows the Vite dev server (port 5173) to call
  the Django API (port 8000) during local development.

• No database by default: the FreeMAD protocol uses InMemorySessionService.
  If you add models later, set DATABASE_URL in .env and uncomment the DB block.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env before anything else so all os.getenv() calls below see the values
load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
# BASE_DIR is the 'backend/' directory (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent

# Where the compiled React build lives inside the container.
# The Dockerfile copies 'frontend/dist/' here after 'npm run build'.
FRONTEND_BUILD_DIR = BASE_DIR / "frontend_build"


# ══════════════════════════════════════════════════════════════════════════════
# CORE DJANGO SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

# SECURITY — change this to a long random string in production.
# Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-change-me-in-production")

# DEBUG must be False in production. Set DEBUG=False in .env on Render.
DEBUG = os.getenv("DEBUG", "True") == "True"

# ALLOWED_HOSTS: add your Render subdomain here, e.g. "myapp.onrender.com"
# In development, localhost + 127.0.0.1 are sufficient.
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")


# ══════════════════════════════════════════════════════════════════════════════
# INSTALLED APPS
# ══════════════════════════════════════════════════════════════════════════════

INSTALLED_APPS = [
    "django.contrib.staticfiles",   # needed for collectstatic
    "corsheaders",                  # django-cors-headers: allow React dev server
    "chat",                         # our app with views.py + freemad/agent.py
]

# No auth, admin, sessions, or messages apps are needed for this API-only
# backend. Add them back if you extend the project.


# ══════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

MIDDLEWARE = [
    # CorsMiddleware MUST be first so it adds headers before any response is sent
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise serves React's static files efficiently (JS, CSS, images, etc.)
    # Must come right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.middleware.common.CommonMiddleware",
]


# ══════════════════════════════════════════════════════════════════════════════
# URL CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

ROOT_URLCONF = "config.urls"


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# (Only needed for the frontend catch-all view — not used by the API)
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],         # We serve index.html via FileResponse, not templates
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    }
]


# ══════════════════════════════════════════════════════════════════════════════
# ASGI APPLICATION
# Uvicorn uses this to find the ASGI app object.
# ══════════════════════════════════════════════════════════════════════════════

ASGI_APPLICATION = "config.asgi.application"


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# Uncomment and configure if you add Django models.
# ══════════════════════════════════════════════════════════════════════════════

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.getenv("DB_NAME", "freemad"),
#         "USER": os.getenv("DB_USER", "postgres"),
#         "PASSWORD": os.getenv("DB_PASSWORD", ""),
#         "HOST": os.getenv("DB_HOST", "localhost"),
#         "PORT": os.getenv("DB_PORT", "5432"),
#     }
# }

# Minimal SQLite config required even if you don't use models,
# because some Django internals reference the DATABASES setting.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# WhiteNoise serves files from FRONTEND_BUILD_DIR at the root URL path.
# e.g. /assets/index-abc123.js is served from frontend_build/assets/index-abc123.js
# ══════════════════════════════════════════════════════════════════════════════

STATIC_URL = "/static/"

# collectstatic gathers files here. Not heavily used since WhiteNoise serves
# directly from FRONTEND_BUILD_DIR, but Django requires this to be set.
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise root: files here are served at the root URL (no /static/ prefix).
# This lets React's /assets/... paths work without any rewriting.
WHITENOISE_ROOT = str(FRONTEND_BUILD_DIR)


# ══════════════════════════════════════════════════════════════════════════════
# CORS (Cross-Origin Resource Sharing)
# Allows the React Vite dev server on port 5173 to call the Django API on 8000.
# In production on Render, both are on the same origin so CORS is irrelevant,
# but it doesn't hurt to keep the setting.
# ══════════════════════════════════════════════════════════════════════════════

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",    # Vite dev server default port
    "http://127.0.0.1:5173",
    "http://localhost:3000",    # Create-React-App fallback, just in case
]

# Allow credentials (cookies, auth headers) to be sent cross-origin.
CORS_ALLOW_CREDENTIALS = True

# Allow the Content-Type header so our JSON POST requests work.
CORS_ALLOW_HEADERS = [
    "accept",
    "content-type",
    "authorization",
]


# ══════════════════════════════════════════════════════════════════════════════
# INTERNATIONALISATION (defaults, can be ignored for a school project)
# ══════════════════════════════════════════════════════════════════════════════

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
