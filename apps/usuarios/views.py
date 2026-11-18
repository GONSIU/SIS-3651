from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, FormView, ListView, UpdateView

from apps.core.mixins import RolRequeridoMixin
from .forms import RegistroClienteForm, RestablecerPasswordForm, UsuarioEditForm, UsuarioForm
from .models import Usuario


class LoginUsuarioView(LoginView):
    template_name = "usuarios/login.html"

    # Pagina de inicio por rol cuando no hay ?next=. Los roles que no aparecen van a
    # LOGIN_REDIRECT_URL (el dashboard). Un ?next= seguro siempre tiene prioridad.
    INICIO_POR_ROL = {"conductor": "viajes:mis_viajes", "cliente": "ventas:mis_pasajes"}

    def get_default_redirect_url(self) -> str:
        # LoginView ya llamo a auth_login(): request.user es el usuario que entro.
        destino = self.INICIO_POR_ROL.get(self.request.user.rol)
        if destino:
            return reverse(destino)
        return super().get_default_redirect_url()


class LogoutUsuarioView(LogoutView):
    pass


class RegistroClienteView(CreateView):
    """Crea la cuenta, inicia sesion y vuelve a ?next= (por ejemplo, el asiento elegido)."""

    form_class = RegistroClienteForm
    template_name = "usuarios/registro.html"

    def _siguiente(self) -> str:
        siguiente = self.request.POST.get("next") or self.request.GET.get("next") or ""
        # Misma proteccion que el login contra redirecciones a otros sitios.
        if url_has_allowed_host_and_scheme(
            siguiente, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return siguiente
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self._siguiente()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Cuenta creada. Ya puedes reservar.")
        return response

    def get_success_url(self) -> str:
        return self._siguiente() or reverse("ventas:mis_pasajes")


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


class RestablecerPasswordView(RolRequeridoMixin, FormView):
    """El admin asigna una contrasena temporal nueva a un usuario que la olvido.

    Al cambiar el hash, Django invalida las sesiones abiertas de ese usuario: cada
    sesion guarda un valor derivado del hash y deja de coincidir."""

    roles_permitidos = ["admin"]
    form_class = RestablecerPasswordForm
    template_name = "usuarios/restablecer_password.html"

    @cached_property
    def usuario(self) -> Usuario:
        # Se busca recien al usarlo, despues del chequeo de rol del mixin: asi quien no
        # es admin recibe 403 y no puede averiguar que pk existen (404).
        return get_object_or_404(Usuario, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.usuario
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuario"] = self.usuario
        return context

    def get_success_url(self):
        return reverse("usuarios:editar", kwargs={"pk": self.usuario.pk})

    def form_valid(self, form):
        form.save()
        if self.usuario.pk == self.request.user.pk:
            # Sin esto, el admin que cambia su propia contrasena perderia su sesion.
            update_session_auth_hash(self.request, self.usuario)
        messages.success(
            self.request,
            f"Contrasena de {self.usuario.username} restablecida. Sus sesiones abiertas se cerraron.",
        )
        return super().form_valid(form)
