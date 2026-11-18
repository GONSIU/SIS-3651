"""Sesion obligatoria en todo el sitio ("denegar por defecto").

Django 5.1 trae LoginRequiredMiddleware; este proyecto usa 5.0, asi que esta es una
version propia y minima de la misma idea. Las vistas protegidas por rol siguen usando
RolRequeridoMixin: este middleware solo cubre al visitante sin sesion, para que una
vista nueva que olvide el mixin no quede publica.
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Vistas accesibles sin sesion, por nombre de URL (namespace:nombre). Usar nombres y
# no rutas evita que un cambio en urls.py abra o cierre algo sin querer.
VISTAS_PUBLICAS = frozenset(
    {
        "core:root",  # "/" solo redirige al login
        "usuarios:login",
        "usuarios:logout",
        "usuarios:registro",  # registro publico de clientes
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
