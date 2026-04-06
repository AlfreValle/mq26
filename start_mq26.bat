@echo off
title MQ26 — Terminal de Inversiones
color 1F

echo.
echo  ============================================================
echo   📈  MQ26 — Terminal de Inversiones BYMA
echo   Puerto: http://localhost:8502
echo  ============================================================
echo.

cd /d "%~dp0"

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado. Verificá que esté en el PATH.
    pause
    exit /b 1
)

:: Verificar streamlit
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Streamlit no instalado. Ejecutá: pip install streamlit
    pause
    exit /b 1
)

echo  Iniciando MQ26 en http://localhost:8502 ...
echo  (La primera carga puede demorar ~10 seg mientras descarga precios)
echo  (Cerrá esta ventana para detener la aplicación)
echo.

:: Abrir el navegador después de 5 segundos (MQ26 tarda más por yfinance)
start /b cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8502"

:: Lanzar la app
python -m streamlit run run_mq26.py ^
    --server.port 8502 ^
    --server.headless false ^
    --theme.primaryColor "#1565C0" ^
    --theme.backgroundColor "#F8F9FA" ^
    --theme.secondaryBackgroundColor "#E3F2FD" ^
    --theme.textColor "#212121" ^
    --browser.gatherUsageStats false

pause
