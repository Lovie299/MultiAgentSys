# chat/urls.py
# URL patterns scoped to the "chat" Django app.
# These are included from config/urls.py under the /api/ prefix.

from django.urls import path
from . import views

urlpatterns = [
    # POST /api/chat/ — SSE streaming endpoint for the FreeMAD protocol
    path("chat/", views.chat_stream, name="chat_stream"),
]
