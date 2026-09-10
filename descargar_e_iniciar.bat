@echo off
setlocal enabledelayedexpansion
title Piano Autoplayer - instalador

REM ============================================================
REM   Este instalador YA NO descarga codigo fuente: baja
REM   directo el programa compilado (.exe) desde un Release
REM   publico de GitHub. Tus companeros nunca ven el codigo.
REM
REM   PONLE AQUI el repo PUBLICO de solo-releases (el que creaste
REM   aparte del repo privado con el codigo):
REM ============================================================
set RELEASES_REPO=https://github.com/GTCruzV/piano-autoplayer-releases
set ZIP_NAME=PianoAutoplayer.zip
set CARPETA=PianoAutoplayer

echo ============================================
echo   Piano Autoplayer - instalador
echo ============================================
echo.

echo Descargando la ultima version...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Invoke-WebRequest -Uri '%RELEASES_REPO%/releases/latest/download/%ZIP_NAME%' -OutFile '%ZIP_NAME%'"
if errorlevel 1 (
    echo.
    echo No se pudo descargar. Revisa tu conexion a internet, o que
    echo ya hayas publicado un Release con un archivo llamado
    echo exactamente "%ZIP_NAME%" en %RELEASES_REPO%
    pause
    exit /b 1
)

echo Descomprimiendo...
if exist "%CARPETA%" rmdir /s /q "%CARPETA%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP_NAME%' -DestinationPath '.' -Force"
if errorlevel 1 (
    echo.
    echo No se pudo descomprimir el archivo descargado.
    pause
    exit /b 1
)
del "%ZIP_NAME%"

if not exist "%CARPETA%\PianoAutoplayer.exe" (
    echo.
    echo Algo salio mal: no encuentro PianoAutoplayer.exe dentro de
    echo "%CARPETA%". Revisa que el .zip del Release tenga esa carpeta
    echo adentro tal cual la genera build.bat.
    pause
    exit /b 1
)

echo.
echo Abriendo el programa...
start "" "%CARPETA%\PianoAutoplayer.exe"

echo.
echo ============================================
echo Listo. La proxima vez que abras este .bat, vuelve a
echo descargar la ultima version automaticamente.
echo Puedes cerrar esta ventana.
echo ============================================
pause
