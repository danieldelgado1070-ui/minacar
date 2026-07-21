@echo off
title Gestion de Compraventa de Vehiculos
cd /d "%~dp0"
echo Iniciando la aplicacion...
echo Se abrira sola en el navegador. NO cierres esta ventana negra mientras la uses.
python app.py
if errorlevel 1 (
  echo.
  echo No se pudo iniciar. Comprueba que Python esta instalado.
  pause
)
