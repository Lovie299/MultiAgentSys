# config/urls.py — Root URL configuration
#
# Routing strategy:
#   /api/chat/  → FreeMAD SSE streaming endpoint  (Django handles this)
#   /*          → React SPA catch-all             (Django serves index.html,
#                                                   React Router takes over)
#
# The API prefix /api/ keeps backend routes clearly separated from frontend
# routes. Add more Django apps under /api/ as the project grows.

from django.urls import path, include
from chat.views import frontend

urlpatterns = [
    # ── API routes ─────────────────────────────────────────────────────────
    # All URLs starting with "api/" are delegated to chat/urls.py
    path("api/", include("chat.urls")),

    # ── React SPA catch-all ────────────────────────────────────────────────
    # This MUST be last. It matches everything that didn't match /api/...
    # and returns the React index.html so client-side routing works.
    # e.g. /  /about  /chat/123  all return index.html
    path("", frontend),          # matches "/"
    path("<path:path>", frontend),  # matches everything else
]
# from django.urls import path, include, re_path
# from chat.views import frontend

# urlpatterns = [
#     # API
#     path("api/", include("chat.urls")),

#     # React SPA (safe catch-all)
#     re_path(r"^(?!api/).*", frontend),
# ]