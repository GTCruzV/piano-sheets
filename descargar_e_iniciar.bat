@echo off
setlocal enabledelayedexpansion
title Piano Autoplayer - instalador

REM ============================================================
REM   PONLE AQUI el link de tu repositorio de GitHub (el normal,
REM   el que se ve en el navegador, terminando SIN ".git"):
REM ============================================================
set REPO_URL=https://github.com/GTCruzV/piano-sheets
set RAMA=main
set CARPETA=piano-autoplayer

echo ============================================
echo   Piano Autoplayer - instalador
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo No encontre Python instalado.
    echo Instalalo desde https://www.python.org/downloads/
    echo ^(en el instalador, marca la casilla "Add python.exe to PATH"^)
    echo y despues vuelve a abrir este archivo.
    pause
    exit /b 1
)

if exist "%CARPETA%\piano_autoplayer.py" (
    echo Ya existe la carpeta "%CARPETA%", voy a actualizarla...
    if exist "%CARPETA%\.git" (
        pushd "%CARPETA%"
        git pull
        popd
    ) else (
        echo ^(esta copia no se hizo con git, la vuelvo a descargar
        echo  completa para asegurarme de que este al dia^)
        rmdir /s /q "%CARPETA%_viejo" 2>nul
        ren "%CARPETA%" "%CARPETA%_viejo" 2>nul
        goto DESCARGAR
    )
    goto INSTALAR
)

:DESCARGAR
echo Descargando el programa desde GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Invoke-WebRequest -Uri '%REPO_URL%/archive/refs/heads/%RAMA%.zip' -OutFile 'piano-autoplayer-descarga.zip'"
if errorlevel 1 (
    echo.
    echo No se pudo descargar. Revisa tu conexion a internet, o que
    echo el link de arriba ^(REPO_URL^) sea correcto y el repositorio
    echo sea publico.
    pause
    exit /b 1
)

echo Descomprimiendo...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'piano-autoplayer-descarga.zip' -DestinationPath '.' -Force"
if errorlevel 1 (
    echo.
    echo No se pudo descomprimir el archivo descargado.
    pause
    exit /b 1
)
del piano-autoplayer-descarga.zip

REM GitHub descomprime la carpeta como "NOMBRE-DEL-REPO-RAMA"
for /d %%D in (*-%RAMA%) do (
    if exist "%%D\piano_autoplayer.py" ren "%%D" "%CARPETA%"
)

:INSTALAR
if not exist "%CARPETA%\piano_autoplayer.py" (
    echo.
    echo Algo salio mal: no encuentro piano_autoplayer.py dentro de
    echo "%CARPETA%". Revisa el link de REPO_URL arriba de este archivo.
    pause
    exit /b 1
)

pushd "%CARPETA%"
echo.
echo Instalando dependencias...
py -m pip install --upgrade pip >nul
py -m pip install -r requirements.txt

echo.
echo Abriendo el programa...
py piano_autoplayer.py
popd

if errorlevel 1 pause
