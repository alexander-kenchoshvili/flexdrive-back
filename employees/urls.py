from django.urls import path
from .views import team_list

urlpatterns = [
    path('team/', team_list)
]