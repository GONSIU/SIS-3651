# Después de clonar el repositorio

Esta guía cubre exactamente qué hacer la primera vez que clonas
`transporte_pasajeros`, tanto para poner el proyecto a correr como para
ubicarte dentro del flujo de ramas (Git Flow) que usa el equipo.

## 1. Clonar y ubicarte en la rama correcta

```bash
git clone https://github.com/tu-organizacion/transporte_pasajeros.git
cd transporte_pasajeros
```

Al clonar, Git te deja parado en `main` por defecto, pero **todo el trabajo
del equipo ocurre a partir de `develop`**, no de `main`. Cámbiate ahí:

```bash
git checkout develop
git pull origin develop
```

Verifica que sí tienes ambas ramas disponibles:

```bash
git branch -a
```

Deberías ver algo como:

```
* develop
  main
  remotes/origin/develop
  remotes/origin/main
```

## 2. Levantar el proyecto localmente

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

> No corras `makemigrations` — las migraciones ya están en el repositorio.
> Solo aplícalas con `migrate`.

Confirma que todo responde:

- App: http://localhost:8000
- Admin: http://localhost:8000/admin

Si algo falla en este paso (puerto ocupado, Docker sin iniciar, etc.), revisa
la sección "Solución de problemas comunes" del `README.md`.

## 3. Crear tu rama de trabajo

Nunca se trabaja directo sobre `develop` ni sobre `main`. Toda funcionalidad,
corrección o tarea nace de `develop` en una rama nueva:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/nombre-app-descripcion-corta
```

Ejemplos de nombres válidos, según lo que vayas a tocar:

```
feature/usuarios-recuperar-password
feature/ventas-reporte-diario
bugfix/viajes-doble-venta-asiento
```

Tipos de prefijo disponibles:

| Prefijo | Cuándo usarlo |
|---|---|
| `feature/` | Una funcionalidad nueva |
| `bugfix/` | Corregir un bug encontrado en `develop` |
| `hotfix/` | Arreglo urgente directo sobre `main` (poco común, lo coordina el líder técnico) |

## 4. Trabajar y subir tus cambios

```bash
git add .
git commit -m "feat(ventas): agregar reporte diario de ventas"
git push -u origin feature/ventas-reporte-diario
```

Usa el prefijo `feat`, `fix`, `docs`, `refactor`, `test` o `chore` en cada
commit (ver `CONTRIBUTING.md` para la lista completa con ejemplos).

## 5. Antes de abrir el Pull Request

Trae los últimos cambios de `develop` a tu rama para reducir conflictos:

```bash
git checkout develop
git pull origin develop
git checkout feature/ventas-reporte-diario
git merge develop
git push
```

## 6. Abrir el Pull Request en GitHub

- **Base:** `develop` — **Compare:** tu rama `feature/...` (nunca contra `main`)
- Completa la checklist del template de PR
- Asigna al menos un revisor
- Espera aprobación antes de mergear
- Elimina tu rama una vez mergeada (GitHub lo sugiere automáticamente)

## Resumen rápido (para tenerlo a mano)

```bash
# Una sola vez, después de clonar:
git checkout develop
git pull origin develop
cp .env.example .env
docker compose build && docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser

# Cada vez que empieces algo nuevo:
git checkout develop
git pull origin develop
git checkout -b feature/mi-tarea

# Mientras trabajas:
git add .
git commit -m "feat(app): descripción del cambio"
git push -u origin feature/mi-tarea
# → abrir Pull Request hacia develop en GitHub
```

Para el detalle completo de la estrategia de ramas, releases y hotfixes, ver
`CONTRIBUTING.md`.
