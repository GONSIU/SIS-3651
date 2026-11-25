"""Sesion obligatoria en todo el sitio ("denegar por defecto").

Django 5.1 trae LoginRequiredMiddleware; este proyecto usa 5.0, asi que esta es una
version propia y minima de la misma idea. Las vistas protegidas por rol siguen usando
RolRequeridoMixin: este middleware solo cubre al visitante sin sesion, para que una
vista nueva que olvide el mixin no quede publica.
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

# Vistas accesibles sin sesion, por nombre de URL (namespace:nombre). Usar nombres y
# no rutas evita que un cambio en urls.py abra o cierre algo sin querer.
VISTAS_PUBLICAS = frozenset(
    {
        "core:root",  # landing publica
        "core:salidas",  # horarios regulares, sin datos de pasajeros
        "core:nosotros",
        "usuarios:login",
        "usuarios:logout",
        "usuarios:registro",  # registro publico de clientes
        # Consulta de viajes y asientos antes de iniciar sesion (REQF 9). Solo muestran
        # datos del viaje y el estado de cada asiento, nunca datos de pasajeros.
        "ventas:buscar_viajes",
        "ventas:viaje_publico",
        "ventas:mapa_publico",
    }
)

# El admin de Django tiene su propio login y sus propios permisos (is_staff).
NAMESPACES_PUBLICOS = frozenset({"admin"})


class LoginObligatorioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # STATIC_URL puede venir sin barra inicial ("static/").
        self.prefijo_static = "/" + settings.STATIC_URL.lstrip("/")

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # process_view corre despues de resolver la URL: hay resolver_match. Una URL
        # inexistente nunca llega aqui y devuelve 404 normalmente.
        if request.user.is_authenticated:
            return None

        match = request.resolver_match
        if match.view_name in VISTAS_PUBLICAS:
            return None
        if NAMESPACES_PUBLICOS.intersection(match.namespaces):
            return None
        # En desarrollo los estaticos pasan por urls.py (static()); la pagina de login
        # necesita su CSS. Los archivos de MEDIA no se exceptuan: exigen sesion.
        if request.path.startswith(self.prefijo_static):
            return None

        return redirect_to_login(request.get_full_path())


# Lo unico que puede usar quien tiene una contrasena temporal: cambiarla o salir.
VISTAS_CON_PASSWORD_TEMPORAL = frozenset({"usuarios:cambiar_password", "usuarios:logout"})


class CambioPasswordObligatorioMiddleware:
    """Manda a cambiar la contrasena a quien tiene debe_cambiar_password.

    Revisarlo solo al iniciar sesion no basta: bastaria escribir otra URL para saltarlo.
    No importa apps.usuarios: lee el atributo con getattr y usa nombres de URL."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefijo_static = "/" + settings.STATIC_URL.lstrip("/")

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(request.user, "debe_cambiar_password", False):
            return None
        if request.resolver_match.view_name in VISTAS_CON_PASSWORD_TEMPORAL:
            return None
        if request.path.startswith(self.prefijo_static):
            return None
        return redirect("usuarios:cambiar_password")
