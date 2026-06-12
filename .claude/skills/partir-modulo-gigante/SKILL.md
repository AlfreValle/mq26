---
name: partir-modulo-gigante
description: Parte un módulo gigante de MQ26 (ui/tab_*.py >1500 líneas, core/renta_fija_ar.py) en slices incrementales y verificables, siguiendo el procedimiento probado de la Fase 2.1. Usar cuando se pida refactorizar, partir o achicar un archivo grande.
---

# Partir módulos gigantes — procedimiento probado (Fase 2.1)

Pendientes conocidos: `ui/tab_inversor.py` (~2800), `core/renta_fija_ar.py`
(~2400), `ui/tab_cartera.py` (~1700), `ui/tab_optimizacion.py` (~1500).
Regla: ningún archivo nuevo > 800 líneas; un slice por commit.

## 1. Mapear

```bash
grep -n "^def \|^class \|^_[A-Z]" <archivo>   # símbolos top-level
```
Para cada símbolo candidato a mover, contar usos y QUIÉN lo usa:
```bash
grep -n "<simbolo>" <archivo>    # líneas de definición y uso
grep -rn "from <modulo> import\|import <modulo>" --include="*.py" .  # importadores externos
```
Criterio: mover (a) secciones autocontenidas con sus helpers exclusivos, o
(b) helpers usados por ≥2 secciones futuras → a un `_helpers.py` del paquete.

## 2. Crear el destino

Paquete `ui/<dominio>/` con `__init__.py` docstrindocumentado. El archivo
original queda como orquestador delgado que importa del paquete.

## 3. Mover con script de spans anclados (NO ediciones a mano en bloques grandes)

Patrón probado — eliminar por número de línea CON validación de anclas:

```python
with open(path, 'rb') as f:
    lines = f.read().decode('utf-8').splitlines(keepends=True)
anchors = {66: 'def _log_degradacion', ...}   # línea → prefijo esperado
for ln, prefix in anchors.items():
    assert lines[ln-1].rstrip('\r\n').startswith(prefix), f'línea {ln} corrida'
out = [l for i, l in enumerate(lines, 1) if i not in drop]
with open(path, 'wb') as f:
    f.write(''.join(out).encode('utf-8'))
```

El repo es **CRLF**: leer/escribir binario o `newline=''` para no corromper EOLs.

## 4. Re-importar y limpiar

- Import del paquete en el orquestador (solo los símbolos que sigue usando).
- `python -m ruff check --fix` se lleva los imports huérfanos.
- Borrar de paso constantes muertas detectadas (grep con 1 solo hit = sospechosa).

## 5. Verificar cada slice

- ruff verde repo completo.
- Suite completa `-n 4` (no solo los tests del módulo — los helpers movidos
  pueden usarse desde flujos lejanos).
- Smoke import del orquestador.
- Commit atómico: `refactor(ui): Fase 2.1 — <qué> (<antes> → <después> líneas)`.
