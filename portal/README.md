# Portal multiusuario · etapa 1

Componente independiente de ComfyUI, Qwen y los motores 3D. Implementa cuentas,
sesiones, roles, referencias privadas y solicitudes de trabajo con propietario.

## Estado

Las solicitudes quedan en **pendiente de motor**. Esta etapa no genera imagenes ni
modelos y no publica ComfyUI. La conexion con la cola y el trabajador corresponde
a la etapa 2 del [plan](../docs/PLAN_ACCESO_USUARIOS.md).

## Arranque local

Desde la raiz del repositorio, con Python 3.11 o posterior:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r portal/requirements.txt
.venv/Scripts/python -m portal crear-usuario administracion --rol administrador
.venv/Scripts/python -m portal servir --local-http
```

La contraseña se solicita en terminal, sin mostrarla ni ponerla en argumentos.
No existe contraseña predeterminada ni registro abierto. Abre
`http://localhost:8090`. Puedes crear otras cuentas desde Administracion o por CLI.

En otros sistemas usa el interprete correspondiente del entorno virtual.
`EXO_PORTAL_DATA` o `--datos` eligen donde guardar SQLite y los archivos; por defecto
se usa `.exo-portal` en la carpeta del usuario, fuera del repositorio.
Los argumentos globales, como `--datos`, van antes de `crear-usuario` o `servir`.

## Separacion de usuarios

- Los clientes y operadores solo acceden a sus referencias, trabajos y resultados.
- Los administradores pueden gestionarlos todos explicitamente.
- Los identificadores del propietario se obtienen de la sesion, no del navegador.
- El administrador no puede mezclar silenciosamente referencias ajenas en un trabajo propio.
- Las rutas locales nunca se aceptan como opciones de un trabajo.
- Las imagenes recibidas se validan, se guardan con nombre aleatorio y sin metadata
  original. Se conserva transparencia, pero no EXIF, prompts ni el archivo original.
- Borrar un trabajo elimina sus resultados y referencias sin otros usos. Una
  referencia usada por otro trabajo se conserva; su borrado directo se rechaza.

## Acceso y despliegue

Sesiones HttpOnly y SameSite=Strict, token CSRF en escrituras y comprobacion de
origen. Las cookies son Secure por defecto. `--local-http` desactiva Secure solo
para desarrollo en localhost; no permite abrir esa configuracion a la red.

El proxy HTTPS de una etapa posterior debe preservar el Host y permitir solo el
portal. `--origen` puede fijar el origen permitido. No se confia en cabeceras de
identidad de Tailscale ni en X-Forwarded-For enviadas por el cliente.
La limitacion de login inicial usa usuario y origen de conexion; los limites de
abuso globales y la configuracion de proxies forman parte del piloto publico.

Esta etapa se valida localmente; no habilita Serve, Funnel ni cambios de firewall.
El esquema de datos es inicial: futuras actualizaciones que lo cambien necesitaran
migraciones y copia de seguridad. Ejecutar una sola instancia del portal en esta etapa.

## Pruebas

```powershell
python -m unittest discover -s portal/tests -v
```

Las pruebas crean cuentas, sesiones, imagenes y SQLite en carpetas temporales.
No requieren modelos, GPU, Tailscale ni una instancia de ComfyUI en ejecucion.


## Validacion de esta entrega (2026-11-27)

26 pruebas API/locales completadas: permisos entre cuentas, bloqueo de grafos y
rutas, sesiones caducadas y revocadas, CSRF, cookie Secure por defecto, origen del
login, administracion, imagenes privadas sin metadata, persistencia, idempotencia
y borrado real de referencias/resultados temporales. Se comprobo sintaxis del JS.

No se abrieron accesos LAN/Tailscale/publicos ni se crearon cuentas reales durante
las pruebas. No se conectaron motores ni se validaron nuevas generaciones. La
prueba de uso en un movil real forma parte de las etapas de acceso posteriores.
