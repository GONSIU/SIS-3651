from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import RegistroClienteForm


class LoginUsuarioView(LoginView):
    template_name = "usuarios/login.html"


class LogoutUsuarioView(LogoutView):
    pass


class RegistroClienteView(CreateView):
    form_class = RegistroClienteForm
    template_name = "usuarios/registro.html"
    success_url = reverse_lazy("usuarios:login")
