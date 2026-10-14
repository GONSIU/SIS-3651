from django.utils import timezone
from django.views.generic import TemplateView
from apps.rutas.models import Ruta
from apps.viajes.models import Viaje
from apps.ventas.models import Pasaje

class IndexView(TemplateView):
    template_name = "rutas/index.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
 
        pasajes_hoy = Pasaje.objects.filter(created_at__date=hoy)
        rutas_totales = Ruta.objects.count()
        rutas_activas = Ruta.objects.filter(activa=True).count()
 
        proximas_salidas = (
            Viaje.objects.filter(fecha_salida=hoy)
            .select_related("ruta__origen", "ruta__destino", "bus", "horario")
            .order_by("horario__hora_salida")[:5]
        )
        for viaje in proximas_salidas:
            total_asientos = viaje.asientos_viaje.count()
            vendidos = viaje.asientos_viaje.filter(estado="vendido").count()
            viaje.ocupacion_texto = f"{vendidos}/{total_asientos}" if total_asientos else "—"
            viaje.ocupacion_pct = int(vendidos / total_asientos * 100) if total_asientos else 0
 
        ventas_recientes = (
            Pasaje.objects.select_related("viaje__ruta__origen", "viaje__ruta__destino")
            .order_by("-created_at")[:5]
        )
 
        context.update(
            {
                "boletos_hoy": pasajes_hoy.count(),
                "rutas_activas": rutas_activas,
                "rutas_totales": rutas_totales,
                "rutas_activas_pct": int(rutas_activas / rutas_totales * 100) if rutas_totales else 0,
                "proximas_salidas": proximas_salidas,
                "ventas_recientes": ventas_recientes,
            }
        )
        return context
 