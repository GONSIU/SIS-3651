from django.urls import path
from . import views

app_name = "usuarios"

urlpatterns = [
    path("login/", views.LoginUsuarioView.as_view(), name="login"),
    path("logout/", views.LogoutUsuarioView.as_view(), name="logout"),
    path("registro/", views.RegistroClienteView.as_view(), name="registro"),
    path("usuarios/", views.ListaUsuariosView.as_view(), name="listado"),
    path("usuarios/nuevo/", views.NuevoUsuarioView.as_view(), name="nuevo"),
    path("usuarios/<int:pk>/editar/", views.EditarUsuarioView.as_view(), name="editar"),
]
