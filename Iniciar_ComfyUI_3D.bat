@echo off
if "%EXO_COMFYUI%"=="" (
  echo Define EXO_COMFYUI con la carpeta que contiene main.py.
  exit /b 1
)
if "%EXO_PYTHON%"=="" set "EXO_PYTHON=python"
if "%EXO_PORT%"=="" set "EXO_PORT=8188"
cd /d "%EXO_COMFYUI%"
"%EXO_PYTHON%" main.py --port %EXO_PORT% > comfy_log.txt 2>&1
