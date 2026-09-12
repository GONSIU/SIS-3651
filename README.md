# Sistema de Venta de Pasajes y Encomiendas

Proyecto Django (MVT) + PostgreSQL, ejecutado con Docker.

## Requisitos previos

- Docker Engine 20.10 o superior
- **Docker Compose V2** (se usa como `docker compose`, con espacio, no `docker-compose`
  con guion). Verifica con:

  ```bash
  docker compose version
  ```

  Si da error "unknown command", instala el plugin:

  ```bash
  sudo apt-get update && sudo apt-get install -y docker-compose-plugin
  ```

## Primeros pasos

1. Copia el archivo de variables de entorno (si no existe ya un `.env`):

   ```bash
   cp .env.example .env
   ```

   Ajusta ahí `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` según necesites.

2. Construye las imágenes:

   ```bash
   docker compose build
   ```

3. **Solo la primera vez que se crea el proyecto** (ya no hace falta si clonaste
   el repo y las migraciones ya existen en `apps/*/migrations/`), genera las
   migraciones iniciales:

   ```bash
   docker compose run --rm --entrypoint python web manage.py makemigrations
   ```

   Esto es necesario una única vez porque el modelo de usuario personalizado
   (`apps.usuarios.Usuario`) debe tener su migración inicial antes de que
   cualquier otra app pueda arrancar.

4. Levanta los servicios (web + base de datos):

   ```bash
   docker compose up -d
   ```

   El `entrypoint.sh` espera a que PostgreSQL esté listo, aplica migraciones
   y recolecta archivos estáticos automáticamente.

5. Crea un superusuario para entrar al admin:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

6. Abre el sistema:

   - Aplicación: http://localhost:8000
   - Admin: http://localhost:8000/admin

## Si clonas el repo (ya con migraciones incluidas)

Los pasos 1, 2, 4, 5 y 6 son iguales. **Sáltate el paso 3** (`makemigrations`) —
las migraciones ya están en el repositorio, solo aplícalas con `migrate`
(esto ya lo hace automáticamente el `entrypoint.sh` al levantar el contenedor,
no necesitas correrlo a mano).

## Comandos útiles

```bash
# Ver logs
docker compose logs -f web

# Ver estado de los contenedores
docker compose ps

# Crear una migración tras modificar modelos
docker compose exec web python manage.py makemigrations

# Aplicar migraciones manualmente
docker compose exec web python manage.py migrate

# Abrir una shell de Django
docker compose exec web python manage.py shell

# Detener todo
docker compose down
```

## Solución de problemas comunes

**`docker: unknown command: docker compose`**
Falta el plugin de Compose V2. Ver sección "Requisitos previos" arriba.

**`Cannot connect to the Docker daemon at unix:///var/run/docker.sock`**
El servicio de Docker no está corriendo.

```bash
sudo systemctl status docker
```

Si aparece `failed to load listeners: no sockets found via socket activation`,
el socket de systemd no está activo:

```bash
sudo systemctl enable --now docker.socket
sudo systemctl restart docker.service
```

Si estás en WSL2 con Docker Desktop (no Docker nativo), asegúrate de que la
integración WSL esté activada en *Docker Desktop → Settings → Resources →
WSL Integration*.

**`Bind for 0.0.0.0:5432 failed: port is already allocated`**
Ya tienes otro PostgreSQL corriendo en tu máquina (de otro proyecto o
instalado localmente) usando el puerto 5432. Este proyecto expone Postgres
en el puerto **5433** hacia tu máquina (ver `docker-compose.yml`) para evitar
justamente este conflicto. Dentro de la red de Docker, el contenedor `web`
sigue hablando con `db:5432` sin problema — el cambio de puerto solo afecta
cómo te conectas desde fuera (ej. con DBeaver o pgAdmin, usarías
`localhost:5433`).

**`ValueError: Dependency on app with no migrations: usuarios`**
Faltan las migraciones iniciales. Corre el paso 3 de "Primeros pasos"
(`makemigrations`) antes de `docker compose up -d`.

**`localhost:5433` muestra `ERR_EMPTY_RESPONSE` en el navegador**
Es normal — 5433 es el puerto de PostgreSQL, no de la aplicación web.
PostgreSQL no habla HTTP, por eso el navegador no puede mostrar nada ahí.
La aplicación está en **http://localhost:8000**.

## Estructura de apps

| App | Responsabilidad |
|---|---|
| usuarios | Autenticación, roles (cliente, ventanillero, supervisor, admin) |
| rutas | Terminales, rutas, horarios |
| flota | Buses, tipos de bus, asientos |
| viajes | Viaje programado (ruta + bus + fecha) y disponibilidad de asientos |
| ventas | Pasajes, pagos, comprobantes, reembolsos |
| encomiendas | Registro y seguimiento de paquetería |
| incidencias | Alertas, reclamos, tickets de soporte |
| reportes | Reportes de ventas diarios/semanales/mensuales |
| personal | Desempeño del personal de ventanilla |
| core | Utilidades compartidas (modelo base, mixins, context processors) |

## Producción

Para producción se usa `docker-compose.prod.yml`, que añade Gunicorn y Nginx,
y fuerza `DJANGO_SETTINGS_MODULE=config.settings.production`:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```