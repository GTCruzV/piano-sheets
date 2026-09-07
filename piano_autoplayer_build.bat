@echo off
echo Instalando dependencias...
py -m pip install --upgrade pip
py -m pip install keyboard pyinstaller

echo.
echo Compilando el .exe...
py -m PyInstaller --onefile --noconsole --name "PianoAutoplayer" piano_autoplayer.py

echo.
echo Listo. El ejecutable esta en la carpeta "dist\PianoAutoplayer.exe"
pause
