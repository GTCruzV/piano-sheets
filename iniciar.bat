@echo off
echo ============================================
echo   Piano Autoplayer - iniciar
echo ============================================
echo.
echo Instalando/actualizando dependencias (si ya estan
echo instaladas esto es rapido, no se vuelven a descargar)...
py -m pip install --upgrade pip >nul
py -m pip install -r requirements.txt

echo.
echo Abriendo el programa...
py piano_autoplayer.py

if errorlevel 1 (
    echo.
    echo ============================================
    echo Algo fallo al abrir el programa. Revisa el
    echo mensaje de arriba. Cosas comunes:
    echo  - No tienes Python instalado o no esta en el PATH
    echo    (reinstala Python y marca "Add python.exe to PATH").
    echo  - Te falto extraer el .zip antes de abrir esta carpeta.
    echo ============================================
    pause
)
