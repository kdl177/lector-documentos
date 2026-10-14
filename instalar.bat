@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Lector de documentos de SIMBAI: instalacion
where python >nul 2>nul || (echo Falta Python 3.11 o superior: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv python -m venv .venv || (echo No se pudo crear el entorno. & pause & exit /b 1)
.venv\Scripts\python -m pip install -r requirements.txt -q || (echo Fallo al instalar las dependencias. & pause & exit /b 1)
echo.
echo Listo. Instala Ollama (https://ollama.com) y ejecuta:
echo   ollama pull qwen3:14b
echo   ollama pull nomic-embed-text
echo Luego abre el lector con iniciar.bat
pause
