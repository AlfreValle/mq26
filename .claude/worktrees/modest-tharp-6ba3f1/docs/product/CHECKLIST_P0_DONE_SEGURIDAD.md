# Checklist P0 Done — Seguridad (RBAC, tenant, auth)

**Versión:** 1.1 · **Referencia:** alineado a [`PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md`](./PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md) · **ID:** P0-RBAC-03 / **P0-TNT-01**

Este documento es la **aceptación formal** de la ola P0 en materia de seguridad de acceso: sin bypass de RBAC, aislamiento de tenant en `db_manager`, y comportamiento **fail-closed** cuando el login por BD falla o se degrada.

---

## 1. Sin bypass RBAC

| # | Criterio | Estado | Evidencia |
|---|----------|--------|-----------|
| 1.1 | Mutaciones en `ui/tab_estudio.py` y `ui/tab_admin.py` pasan por `can_action` / `panel_admin_write` (no solo rol implícito en el título del tab). | OK | Inventario §4a en PENDIENTES; implementación en tabs. |
| 1.2 | Política centralizada en `ui/rbac.py` (`ACTION_POLICY`); acciones desconocidas = deny por defecto (`can_action` sin entrada → `default=False`). | OK | `ui/rbac.py`; tests desconocidos en `tests/test_rbac_p0_policy.py`. |
| 1.3 | Regresión automática: matriz rol × acción cubierta por tests. | OK | `tests/test_rbac_p0_policy.py` (parametrizado desde `ACTION_POLICY`). |

**Cierre bloque RBAC:** los ítems 1.1–1.3 se consideran **cumplidos** con la evidencia indicada.

---

## 2. Sin brechas de tenant (multi-tenant)

| # | Criterio | Estado | Evidencia / notas |
|---|----------|--------|---------------------|
| 2.1 | Lecturas/escrituras sensibles que filtran por `tenant_id` (notas asesor, usuarios app, transacciones). | OK | `guardar_notas_asesor`, `registrar_transaccion`, `create_app_usuario` / `set_app_usuario_clientes` con `cliente_id` validado al tenant. |
| 2.2 | Endurecimiento **P0-TNT-01**: sin fugas en fallbacks SQL ni mutaciones sin comprobar tenant. | OK | `_cliente_pertenece_tenant` alineado con listado default (NULL/vacío/default); `obtener_clientes_df` / `obtener_cliente` (rama migración) filtran por tenant; `actualizar_cliente` y `delete_app_usuario(..., tenant_id=...)` rechazan cruces; UI sin `obtener_clientes_df()` sin tenant en fallbacks; `sincronizar_excel_a_bd(..., tenant_id=)`; `tests/test_tenant_p0_tnt01.py`. |

**Regla de mantenimiento:** nuevas funciones que lean/escriban `clientes` o `app_usuarios` deben filtrar por `tenant_id` o delegar en `db_manager`.

---

## 3. Auth degradada fail-closed

| # | Criterio | Estado | Evidencia |
|---|----------|--------|-----------|
| 3.1 | Con login por BD requerido (`try_database_users` + `db_tenant_id`), si falla el lookup a BD **no** se acepta automáticamente el login por variables de entorno (sin bypass silencioso). | OK | `core/auth.py`: rama `db_required` + comentario fail-closed; única excepción documentada: **breakglass** (`MQ26_BREAKGLASS_*`). |
| 3.2 | Fallo de BD en autenticación marca degradación visible (`{app_id}_degraded_auth`) y log de advertencia. | OK | `core/auth.py` (excepción en `authenticate_app_user`); UI puede mostrar caption (p. ej. tab Admin / degradaciones). |
| 3.3 | Rate limit / bloqueo por intentos fallidos activo en el flujo de login estándar. | OK | `_esta_bloqueado`, `_MAX_FAILED_ATTEMPTS` en `core/auth.py`. |

---

## Veredicto resumido

| Pilar | Listo para producción (con matices) |
|-------|-------------------------------------|
| RBAC | Sí — checklist 1.x cumplida. |
| Tenant | Sí — criterios 2.1–2.2 cumplidos con P0-TNT-01 (regresión en `tests/test_tenant_p0_tnt01.py` + `tests/test_multitenant.py`). |
| Auth fail-closed | Sí — checklist 3.x cumplida. |

**P0-RBAC-03** y **P0-TNT-01** quedan reflejados en esta versión del checklist.

---

*Marco: comité expertos carteras AR — trazabilidad y honestidad operativa.*
