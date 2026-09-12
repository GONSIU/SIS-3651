# Guía de Contribución

Este documento define cómo trabajamos con Git y GitHub en el proyecto
**Sistema de Venta de Pasajes y Encomiendas**. Su objetivo es evitar
conflictos de código, mantener un historial claro y asegurar que `main`
siempre esté en un estado desplegable.

## Estrategia de ramas (Git Flow simplificado)

```
main                    → Código en producción, siempre estable
  └── develop           → Rama de integración de todas las funcionalidades
        ├── feature/...
        ├── bugfix/...
        └── release/...
  └── hotfix/...         → Sale directo de main para arreglos urgentes
```

| Rama | Propósito | Quién le hace push directo |
|---|---|---|
| `main` | Código en producción | Nadie (solo vía Pull Request) |
| `develop` | Integración de funcionalidades terminadas | Nadie (solo vía Pull Request) |
| `feature/*` | Una funcionalidad específica | El desarrollador asignado |
| `bugfix/*` | Corrección de un bug detectado en `develop` | El desarrollador asignado |
| `release/*` | Preparación de una versión antes de pasar a `main` | Líder técnico / QA |
| `hotfix/*` | Arreglo urgente directamente en producción | Líder técnico |

**Regla de oro:** nadie hace `git push` directo a `main` ni a `develop`.
Todo cambio entra mediante Pull Request revisado por al menos una persona.

## Convención de nombres de ramas

Formato: `tipo/descripcion-corta-en-kebab-case`, usando como referencia el
nombre de la app de Django que se está modificando.

```
feature/usuarios-login
feature/ventas-registro-pasaje
feature/encomiendas-seguimiento
feature/reportes-dashboard-mensual
bugfix/viajes-doble-venta-asiento
hotfix/ventas-error-comprobante-pdf
release/v1.0.0
```

## Convención de mensajes de commit

Usamos [Conventional Commits](https://www.conventionalcommits.org/es/) para
mantener un historial legible y poder generar changelogs automáticos.

```
feat(app): nueva funcionalidad
fix(app): corrección de un bug
docs: cambios en documentación
refactor(app): cambio de código sin alterar el comportamiento
test(app): agregar o modificar tests
chore: tareas de mantenimiento (dependencias, configuración, etc.)
style(app): cambios de formato que no afectan la lógica
```

Ejemplos reales para este proyecto:

```
feat(encomiendas): agregar modelo SeguimientoEncomienda
fix(viajes): evitar doble venta de asiento con select_for_update
docs(readme): actualizar instrucciones de docker compose
refactor(ventas): extraer lógica de reembolso a services.py
```

## Flujo de trabajo paso a paso

### 1. Antes de empezar una nueva funcionalidad

```bash
git checkout develop
git pull origin develop
git checkout -b feature/ventas-registro-pasaje
```

### 2. Mientras trabajas

Haz commits pequeños y frecuentes, cada uno con un propósito claro:

```bash
git add .
git commit -m "feat(ventas): agregar modelo Pasaje y migración inicial"
git commit -m "feat(ventas): agregar vista de registro de venta en ventanilla"
git push -u origin feature/ventas-registro-pasaje
```

### 3. Antes de abrir el Pull Request

Actualiza tu rama con los últimos cambios de `develop` para reducir
conflictos en la revisión:

```bash
git checkout develop
git pull origin develop
git checkout feature/ventas-registro-pasaje
git merge develop
# resuelve conflictos si aparecen, luego:
git push
```

### 4. Abrir el Pull Request

- **Base:** `develop` — **Compare:** tu rama `feature/...`
- Usa el template de PR (ver `.github/pull_request_template.md`)
- Asigna al menos un revisor
- Espera la aprobación y que pasen los checks automáticos antes de mergear
- Usa **Squash and merge** para mantener el historial de `develop` limpio
- Elimina la rama después del merge (GitHub lo sugiere automáticamente)

### 5. Preparar una nueva versión (release)

```bash
git checkout develop
git pull origin develop
git checkout -b release/v1.0.0
# pruebas finales, ajustes menores, actualizar versión/changelog
git push -u origin release/v1.0.0
```

Se abre un Pull Request de `release/v1.0.0` → `main`. Al aprobarse y
mergearse:

```bash
git checkout main
git pull origin main
git tag -a v1.0.0 -m "Versión 1.0.0"
git push origin v1.0.0

# No olvides devolver los cambios de la release a develop:
git checkout develop
git merge main
git push origin develop
```

### 6. Arreglar un error urgente en producción (hotfix)

```bash
git checkout main
git pull origin main
git checkout -b hotfix/fix-error-login
# arreglar el problema
git commit -m "fix(usuarios): corregir error de sesión en login"
git push -u origin hotfix/fix-error-login
```

Se abren **dos** Pull Requests: `hotfix/...` → `main` y `hotfix/...` →
`develop`, para que el arreglo no se pierda en la siguiente release.

## Reglas de protección en GitHub

Configurar en **Settings → Branches → Branch protection rules** para
`main` y `develop`:

- ✅ Require a pull request before merging
- ✅ Require at least 1 approval before merging
- ✅ Require status checks to pass before merging (una vez configurado CI)
- ✅ Require branches to be up to date before merging
- ✅ Do not allow force pushes
- ✅ Do not allow deletion of the branch

## División del trabajo por apps

Cada app de Django es un área independiente. Para minimizar conflictos de
merge, se recomienda que cada persona (o pareja) tenga asignadas una o dos
apps como responsabilidad principal:

| App | Responsable sugerido |
|---|---|
| `usuarios` | — |
| `rutas` / `flota` | — |
| `viajes` | — |
| `ventas` | — |
| `encomiendas` | — |
| `incidencias` | — |
| `reportes` | — |
| `promociones` | — |
| `personal` | — |
| `core` | Responsabilidad compartida — cualquier cambio aquí requiere avisar al equipo, ya que lo usan todas las apps |

## Checklist antes de abrir un Pull Request

- [ ] El código corre sin errores: `docker compose exec web python manage.py check`
- [ ] Se generaron las migraciones si hubo cambios en modelos: `makemigrations`
- [ ] Se probó la funcionalidad manualmente en local
- [ ] Los mensajes de commit siguen la convención descrita arriba
- [ ] La rama está actualizada con `develop`
- [ ] No se subieron archivos sensibles (`.env`, credenciales, etc.)
