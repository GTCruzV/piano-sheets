@echo off
echo ============================================
echo   Piano Autoplayer - generador de .exe
echo ============================================
echo.
echo Instalando dependencias...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt

echo.
echo Compilando el programa (incluye la carpeta "web" y el icono,
echo y todo lo que necesita Python; tus companeros NO necesitan
echo instalar nada). Se usa --onedir en vez de --onefile: con
echo --onefile el programa se autodescomprimia en una carpeta
echo temporal CADA VEZ que lo abrias, y eso era lo que lo hacia
echo tardarse mucho / quedarse "(No responde)" casi siempre...
py -m PyInstaller --onedir --noconsole --name "PianoAutoplayer" ^
    --icon "assets\icon.ico" ^
    --add-data "web;web" ^
    piano_autoplayer.py

echo.
echo ============================================
echo Listo. Tu programa esta en la carpeta: dist\PianoAutoplayer\
echo Comprime ESA CARPETA COMPLETA (botón derecho -^> Enviar a -^>
echo Carpeta comprimida) y eso es lo que le pasas a tus companeros.
echo Ya no es un solo .exe suelto: adentro de esa carpeta viene
echo PianoAutoplayer.exe junto con todo lo que necesita para abrir
echo rapido, sin descomprimirse cada vez.
echo ============================================
pause