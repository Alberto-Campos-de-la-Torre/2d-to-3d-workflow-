@echo off
REM ComfyUI solo accesible desde este PC (127.0.0.1). No cambiar a 0.0.0.0.
REM La salida va a comfy_log.txt en vez de a la consola: si la ventana entra en modo
REM seleccion (un clic dentro basta), Windows congela el proceso en la siguiente
REM escritura y el servidor deja de responder aunque el puerto siga abierto.
cd /d D:\AI3D\ComfyUI_windows_portable
echo Arrancando ComfyUI... registro en D:\AI3D\comfy_log.txt
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --listen 127.0.0.1 --port 8188 > D:\AI3D\comfy_log.txt 2>&1
echo.
echo ComfyUI se ha cerrado. Mira D:\AI3D\comfy_log.txt para ver por que.
pause
