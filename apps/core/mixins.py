from django.contrib.auth.mixins import UserPassesTestMixin


class RolRequeridoMixin(UserPassesTestMixin):
    """Restringe el acceso a una vista según el rol del usuario autenticado.

    Uso:
        class MiVista(RolRequeridoMixin, View):
            roles_permitidos = ["ventanillero", "supervisor"]
    """
    roles_permitidos: list[str] = []

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and getattr(user, "rol", None) in self.roles_permitidos
