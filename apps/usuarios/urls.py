from django.urls import path
from . import views

app_name = "usuarios"

urlpatterns = [
    path("login/", views.LoginUsuarioView.as_view(), name="login"),
    path("logout/", views.LogoutUsuarioView.as_view(), name="logout"),
    path("registro/", views.RegistroClienteView.as_view(), name="registro"),
]
