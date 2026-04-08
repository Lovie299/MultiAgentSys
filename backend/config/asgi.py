"""
config/asgi.py — ASGI application entry point

ASGI (Asynchronous Server Gateway Interface) is the async successor to WSGI.
We need it because:
  1. Our chat view is declared   async def chat_stream(...)
  2. StreamingHttpResponse with an async generator requires ASGI
  3. Uvicorn (our server) speaks ASGI

The Uvicorn command in the Dockerfile references this file:
    uvicorn config.asgi:application --host 0.0.0.0 --port 8000
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 'application' is the object Uvicorn looks for by convention.
application = get_asgi_application()
