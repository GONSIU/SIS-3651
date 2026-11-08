from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Usuario

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"
CHECKBOX_CLASSES = "h-4 w-4 accent-signal-orange"


class RegistroClienteForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "email", "first_name", "last_name", "telefono", "ci")


class UsuarioForm(forms.ModelForm):
    """Alta de personal por el admin, con contrasena temporal.

    Es un ModelForm: full_clean() ejecuta la normalizacion, los validadores y
    Usuario.clean() (terminal obligatoria para ventanillero y supervisor). La contrasena
    no es campo del modelo: la vista la guarda con set_password()."""

    # Los clientes se registran solos en la pagina publica.
    ROLES_ALTA = [opcion for opcion in Usuario.ROL_CHOICES if opcion[0] != "cliente"]

    password_temporal = forms.CharField(
        label="Contrasena temporal",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASSES, "autocomplete": "new-password"}),
    )

    class Meta:
        model = Usuario
        fields = [
            "username", "first_name", "last_name", "email",
            "ci", "telefono", "rol", "terminal_asignado",
        ]
        labels = {
            "username": "Usuario",
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo electronico",
            "ci": "CI",
            "telefono": "Telefono",
            "rol": "Rol",
            "terminal_asignado": "Terminal asignado",
        }
        widgets = {
            "username": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. jperez"}),
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Juan Carlos"}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Perez Rojas"}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. jperez@transnaser.bo"}),
            "ci": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 1234567-1B"}),
            "telefono": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 71234567"}),
            "rol": forms.Select(attrs={"class": SELECT_CLASSES}),
            "terminal_asignado": forms.Select(attrs={"class": SELECT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"].choices = self.ROLES_ALTA
        self.fields["rol"].initial = "ventanillero"

    def _post_clean(self):
        # Igual que UserCreationForm: se valida despues de construir la instancia para
        # que UserAttributeSimilarityValidator compare con usuario, nombre y correo.
        super()._post_clean()
        password = self.cleaned_data.get("password_temporal")
        if password:
            try:
                validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password_temporal", error)


class UsuarioEditForm(forms.ModelForm):
    """Edicion de rol, terminal y estado. No toca la contrasena.

    Protecciones: el ultimo admin activo no pierde el rol ni se desactiva, y un admin
    no puede quitarse el rol ni desactivarse a si mismo."""

    class Meta:
        model = Usuario
        fields = ["rol", "terminal_asignado", "is_active"]
        labels = {
            "rol": "Rol",
            "terminal_asignado": "Terminal asignado",
            "is_active": "Cuenta activa",
        }
        widgets = {
            "rol": forms.Select(attrs={"class": SELECT_CLASSES}),
            "terminal_asignado": forms.Select(attrs={"class": SELECT_CLASSES}),
            "is_active": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASSES}),
        }

    def __init__(self, *args, editor: Usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor

    def clean(self):
        cleaned_data = super().clean()
        # En clean() la instancia aun tiene los valores guardados: los del formulario
        # se le aplican despues, en _post_clean().
        usuario = self.instance
        if usuario.rol != "admin":
            return cleaned_data

        pierde_rol = "rol" in cleaned_data and cleaned_data["rol"] != "admin"
        se_desactiva = usuario.is_active and not cleaned_data.get("is_active", False)
        if not (pierde_rol or se_desactiva):
            return cleaned_data

        if usuario.pk == self.editor.pk:
            motivo = "No puedes quitarte el rol de administrador ni desactivar tu propia cuenta."
        elif usuario.es_ultimo_admin_activo():
            motivo = "Es el unico administrador activo: el sistema se quedaria sin administrador."
        else:
            return cleaned_data

        if pierde_rol:
            self.add_error("rol", motivo)
        if se_desactiva:
            self.add_error("is_active", motivo)
        return cleaned_data
