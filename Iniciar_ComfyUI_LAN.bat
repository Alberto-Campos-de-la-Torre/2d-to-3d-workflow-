@echo off
REM ---------------------------------------------------------------------------
REM Arranca ComfyUI accesible desde la RED LOCAL (moviles, tablets, otros PC).
REM
REM CUIDADO: ComfyUI NO PIDE CONTRASENA. Quien alcance este puerto puede generar,
REM ver todo lo generado, subir archivos y lanzar flujos que leen y escriben en
REM las carpetas de ComfyUI. Usalo solo en una red de confianza (tu taller, tu
REM casa), nunca en una wifi publica ni abriendo el puerto en el router.
REM
REM Para que otros equipos lleguen hay que permitir el puerto 8188 en el
REM cortafuegos UNA VEZ. Abre PowerShell COMO ADMINISTRADOR y pega:
REM
REM   New-NetFirewallRule -DisplayName "ComfyUI Exo (LAN)" -Direction Inbound ^
REM     -Protocol TCP -LocalPort 8188 -Action Allow -Profile Private ^
REM     -RemoteAddress LocalSubnet
REM
REM Eso lo limita a tu subred y solo en redes marcadas como privadas. Para
REM quitarlo: Remove-NetFirewallRule -DisplayName "ComfyUI Exo (LAN)"
REM ---------------------------------------------------------------------------
cd /d D:\AI3D\ComfyUI_windows_portable
echo.
echo Arrancando ComfyUI en la red local. Registro en D:\AI3D\comfy_log.txt
echo.
echo Desde el movil, en el navegador, entra en una de estas direcciones:
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' } | ForEach-Object { '    http://' + $_.IPAddress + ':8188/exo/estudio' }"
echo.
echo (si sale mas de una, prueba la de tu wifi; si ninguna responde, falta la
echo  regla del cortafuegos que hay explicada dentro de este archivo)
echo.
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --listen 0.0.0.0 --port 8188 > D:\AI3D\comfy_log.txt 2>&1
echo.
echo ComfyUI se ha cerrado. Mira D:\AI3D\comfy_log.txt para ver por que.
pause
