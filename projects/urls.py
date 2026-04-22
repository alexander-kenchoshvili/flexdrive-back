from django.urls import path
from .views import project_list

urlpatterns = [
    path('projects/', project_list)
]