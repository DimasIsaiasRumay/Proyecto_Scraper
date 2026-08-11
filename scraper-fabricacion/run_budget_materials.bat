@echo off
title Scraper de Fabricacion - Materiales por Producto (Presupuesto)
echo ===================================================
echo Extrayendo materiales por producto (con dimensiones)...
echo Requiere que el scraper principal ya haya corrido antes.
echo ===================================================
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
%PYRUN% extraer_materiales_presupuesto.py
echo ===================================================
echo Proceso finalizado.
echo ===================================================
pause
