@echo off
echo ============================================
echo   Piano Autoplayer - generador de .exe
echo ============================================
echo.
echo Instalando dependencias...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt

echo.
echo Compilando el .exe (incluye la carpeta "web" y el icono,
echo y todo lo que necesita Python; tus companeros NO necesitan
echo instalar nada)...
py -m PyInstaller --onefile --noconsole --name "PianoAutoplayer" ^
    --icon "assets\icon.ico" ^
    --add-data "web;web" ^
    piano_autoplayer.py

echo.
echo ============================================
echo Listo. El ejecutable esta en: dist\PianoAutoplayer.exe
echo Eso es lo UNICO que le tienes que pasar a tus companeros.
echo ============================================
pause