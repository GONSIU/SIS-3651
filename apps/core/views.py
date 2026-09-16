"""from django.views.generic import TemplateView

# Vistas de la app "core"""
from django.shortcuts import redirect

def root_redirect(request):
    return redirect("usuarios:login")  # usa el namespace de la app
