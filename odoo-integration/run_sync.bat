@echo off
REM run_sync.bat — Ejecutar sincronización con Odoo manualmente
REM Uso: doble clic o ejecutar desde terminal

echo ============================================
echo   Sincronizacion de Ubicaciones de Produccion con Odoo
echo ============================================
echo.

cd /d "%~dp0"
REM Preferir Python 3.10 (version de referencia en produccion). Si el launcher
REM "py" no esta o no tiene esa version instalada, usar el "python" del PATH
REM o del entorno virtual activo, en vez de fallar sin explicacion.
py -3.10 -c "" >nul 2>nul
if errorlevel 1 (
    set "PYRUN=python"
) else (
    set "PYRUN=py -3.10"
)
%PYRUN% odoo_sync.py %*

echo.
echo Sincronizacion finalizada.
pause
