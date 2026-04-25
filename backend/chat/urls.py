# chat/urls.py
# URL patterns scoped to the "chat" Django app.
# These are included from config/urls.py under the /api/ prefix.

from django.urls import path
from . import views

urlpatterns = [
    # Main chat endpoint (add this line)
    path('chat/', views.chat_view, name='chat'),
    
   # Debate endpoints
    path('chat/stream/', views.chat_stream, name='chat_stream'),
    
    # Dataset endpoints (NEW)
    path('chat/quick/', views.quick_answer, name='quick_answer'),
    path('dataset/search/', views.search_dataset, name='search_dataset'),
    path('dataset/stats/', views.dataset_stats, name='dataset_stats'),
]
