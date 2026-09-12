from django.contrib.auth.forms import UserCreationForm
from .models import Usuario


class RegistroClienteForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "email", "first_name", "last_name", "telefono", "ci")
