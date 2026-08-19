@echo off
title Scraper de Fabricacion - Ejecucion Manual
echo ===================================================
echo Iniciando Scraper de Fabricacion (Modo Manual)...
echo Incluye scraping + sync con Odoo + materiales de Presupuesto.
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
%PYRUN% main.py --force --sync --presupuesto
echo ===================================================
echo Proceso finalizado.
echo ===================================================
pause
