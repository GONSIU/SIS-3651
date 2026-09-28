from django.urls import path
from . import views

app_name = "personal"

urlpatterns = [
    path("", views.ListaPersonalView.as_view(), name="listado"),
]
