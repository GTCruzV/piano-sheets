@echo off
echo Instalando dependencias...
pip install keyboard pyinstaller

echo.
echo Compilando el .exe...
pyinstaller --onefile --noconsole --name "PianoAutoplayer" piano_autoplayer.py

echo.
echo Listo. El ejecutable esta en la carpeta "dist\PianoAutoplayer.exe"
pause
