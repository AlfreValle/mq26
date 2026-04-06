@echo off
title MQ26 — Verificación de Calidad de Código
color 0E

echo.
echo  ============================================================
echo   MQ26 + DSS Alfredo — Dev Quality Check
echo  ============================================================
echo.

cd /d "%~dp0"

set ERRORS=0

echo [1/3] Ejecutando Ruff (linter)...
python -m ruff check core/ services/ ui/ --ignore E501,B008
if errorlevel 1 (
    echo  [FAIL] Ruff encontro errores.
    set ERRORS=1
) else (
    echo  [OK]   Ruff sin errores.
)
echo.

echo [2/3] Ejecutando mypy (type checker)...
python -m mypy core/ --ignore-missing-imports --no-error-summary 2>nul
if errorlevel 1 (
    echo  [WARN] mypy encontro problemas de tipado.
) else (
    echo  [OK]   mypy sin errores criticos.
)
echo.

echo [3/3] Ejecutando pytest (tests)...
python -m pytest tests/ -v --tb=short -q 2>&1
if errorlevel 1 (
    echo  [FAIL] Algunos tests fallaron.
    set ERRORS=1
) else (
    echo  [OK]   Todos los tests pasaron.
)
echo.

echo  ============================================================
if %ERRORS%==0 (
    echo   RESULTADO: Todo OK - listo para commit
) else (
    echo   RESULTADO: Hay errores - revisar antes de commitear
)
echo  ============================================================
echo.
pause
