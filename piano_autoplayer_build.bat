@echo off
REM Este script quedo desactualizado: no instalaba pywebview/requests/
REM flask/werkzeug ni empacaba la carpeta "web" ni el icono, asi que el
REM .exe salia roto (sin Tienda y sin interfaz). Usa build.bat en su
REM lugar; este archivo ahora solo llama a build.bat para evitar que
REM alguien lo use por error y genere un .exe incompleto.
call build.bat