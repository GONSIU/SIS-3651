from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import RolRequeridoMixin
from .forms import RegistroClienteForm, UsuarioEditForm, UsuarioForm
from .models import Usuario


class LoginUsuarioView(LoginView):
    template_name = "usuarios/login.html"


class LogoutUsuarioView(LogoutView):
    pass


class RegistroClienteView(CreateView):
    form_class = RegistroClienteForm
    template_name = "usuarios/registro.html"
    success_url = reverse_lazy("usuarios:login")


class ListaUsuariosView(RolRequeridoMixin, ListView):
    """Listado con filtros opcionales ?rol=<rol> y ?activo=1|0, combinables."""

    roles_permitidos = ["admin"]
    model = Usuario
    template_name = "usuarios/listado.html"
    context_object_name = "usuarios"

    def _filtros(self) -> tuple[str, str]:
        """Devuelve (rol, activo) validados; un valor desconocido se ignora."""
        rol = self.request.GET.get("rol", "")
        activo = self.request.GET.get("activo", "")
        roles_validos = {clave for clave, _ in Usuario.ROL_CHOICES}
        return (
            rol if rol in roles_validos else "",
            activo if activo in ("1", "0") else "",
        )

    def get_queryset(self):
        rol, activo = self._filtros()
        usuarios = Usuario.objects.select_related("terminal_asignado").order_by(
            "-is_active", "rol", "username"
        )
        if rol:
            usuarios = usuarios.filter(rol=rol)
        if activo:
            usuarios = usuarios.filter(is_active=activo == "1")
        return usuarios

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rol, activo = self._filtros()
        context.update(
            {
                "roles": Usuario.ROL_CHOICES,
                "filtro_rol": rol,
                "filtro_activo": activo,
                "total_usuarios": Usuario.objects.count(),
                "total_activos": Usuario.objects.filter(is_active=True).count(),
                "total_admins": Usuario.objects.filter(rol="admin", is_active=True).count(),
            }
        )
        return context


class NuevoUsuarioView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["admin"]
    model = Usuario
    form_class = UsuarioForm
    template_name = "usuarios/nuevo.html"
    success_url = reverse_lazy("usuarios:listado")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Solo se guarda el hash; el admin no vuelve a ver la contrasena.
        self.object.set_password(form.cleaned_data["password_temporal"])
        self.object.save()
        messages.success(
            self.request, f"Usuario {self.object.username} creado con contrasena temporal."
        )
        return HttpResponseRedirect(self.get_success_url())


class EditarUsuarioView(RolRequeridoMixin, UpdateView):
    roles_permitidos = ["admin"]
    model = Usuario
    form_class = UsuarioEditForm
    template_name = "usuarios/editar.html"
    context_object_name = "usuario"
    success_url = reverse_lazy("usuarios:listado")

    def get_queryset(self):
        return Usuario.objects.select_related("terminal_asignado")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs

    def post(self, request, *args, **kwargs):
        # Bloquea a los admins activos hasta el commit: si dos admins se degradan
        # entre si a la vez, el segundo espera y ya ve que el otro dejo de ser admin.
        with transaction.atomic():
            list(Usuario.objects.select_for_update().filter(rol="admin", is_active=True))
            return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Usuario {self.object.username} actualizado.")
        return response
