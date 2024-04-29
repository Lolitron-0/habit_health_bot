from django.urls import path
from bot import views

urlpatterns = [
    path('users/', views.list_users),
]