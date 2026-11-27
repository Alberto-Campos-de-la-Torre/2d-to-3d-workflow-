# Plan de servicio privado y publico

## Punto de partida

- Modulos 2D y 3D separados, instalables solos o combinados mediante `instalar.py`.
- Base auditada: commit `83001b4`; pesos, resultados y configuracion privada excluidos.
- Las interfaces actuales usan la API general de ComfyUI y comparten catalogo.
- La ausencia de secretos publicados no convierte la instalacion en multiusuario.

## Arquitectura objetivo

Usuario con Tailscale -> HTTPS privado -> portal con cuentas -> cola -> trabajador local.
Usuario sin Tailscale -> HTTPS publico -> mismo portal -> misma cola -> trabajador local.
El trabajador ejecuta plantillas autorizadas de los motores 2D/3D. ComfyUI, modelos,
LLM y API administrativa permanecen privados. El navegador no envia grafos arbitrarios.

El portal sera un componente independiente: no requiere pesos, GPU ni los paquetes
de mallas. La generacion seguira en el equipo del taller. Una instancia inicial
del portal puede usar SQLite; el almacenamiento de archivos se mantiene privado.

## Etapas y criterios de aceptacion

### 1. Cuentas y aislamiento de datos — primera implementacion

- Inicio de sesion, cierre, sesiones con caducidad y usuarios creados por administrador.
- Roles administrador, operador y cliente. La red de acceso no decide el rol.
- Propietario obligatorio para cada referencia, trabajo y archivo generado.
- Endpoints propios del portal, sin proxy general a `/prompt`, `/history`, `/view` o `/ws`.
- Historial y descargas filtrados por usuario; borrado ligado a ese propietario.
- Rutas y nombres de archivos generados en servidor, sin aceptar rutas locales del cliente.
- Interfaz responsive de acceso, referencias y trabajos.

Aceptacion: dos cuentas no pueden consultar, descargar, cancelar ni borrar datos
ajenos aunque conozcan sus identificadores. Un administrador puede gestionarlos
explicitamente. Probar rutas, sesiones, borrado y persistencia tras reiniciar.

Esta etapa no habilita acceso publico ni ejecuta generacion: primero se prueba la
base de identidad y almacenamiento. Los trabajos solicitados quedan pendientes
de la conexion con el trabajador de la etapa 2 y se identifican como tales.

### 2. Cola y trabajador local

- Cola persistente con estados pendiente, ejecutando, terminado, fallido y cancelado.
- Una tarea pesada por GPU, aunque los modulos esten separados.
- Limites configurables por cuenta, resolucion y numero de reintentos.
- Recuperacion tras reiniciar, identificadores idempotentes y cancelacion por propietario.
- Traducir solicitudes del portal a plantillas controladas; validar todas las opciones.
- Publicar progreso y resultados solo al propietario, sin difundir eventos globales.
- Importar al nuevo catalogo solo resultados con procedencia comprobada.

Aceptacion: dos usuarios comparten la GPU sin carreras, duplicados ni cruce de
archivos; un fallo o desconexion no pierde la cola ni deja trabajos eternamente activos.

### 3. Piloto privado con Tailscale

- HTTPS mediante Serve y permisos de red limitados al portal.
- Compartir unicamente el servidor cuando el invitado use otra tailnet.
- Mantener ComfyUI y LLM en sus interfaces privadas; revisar permisos amplios existentes.
- Usar identidad de Serve solo desde su proxy de confianza; conservar roles en la app.

Aceptacion: el invitado usa el portal, pero no alcanza la API bruta de ComfyUI ni
otros equipos o servicios del taller. Revocar su acceso debe impedir nuevas solicitudes.

### 4. Piloto publico para usuarios sin Tailscale

- Funnel frente al portal autenticado, con entrada distinta del acceso privado.
- No publicar ComfyUI. Funnel no sustituye autenticacion ni permisos por archivo.
- Sesiones seguras, proteccion CSRF, limites de carga, cuotas y control de intentos.
- Validar movil mediante datos moviles y Tailscale desconectado.
- Probar subida, progreso, descarga, borrado y retorno tras cerrar el navegador.

Aceptacion: el usuario externo solo utiliza su cuenta; visitantes sin sesion no
pueden generar ni acceder a referencias, historial o resultados. Medir transferencias
reales antes de usar Funnel para archivos grandes.

### 5. Servicio estable

- Portal publico con dominio propio en un servidor independiente del equipo GPU.
- El trabajador local consulta la cola mediante Tailscale, sin exponer su API al publico.
- El portal informa cuando el motor esta desconectado y conserva trabajos pendientes.
- Copias de seguridad, retencion, cuotas de almacenamiento y descargas controladas.
- Previsualizaciones ligeras; las mallas originales enormes no son descargas por defecto.

## Despliegue y seguridad

- Credenciales, claves y configuracion de red permanecen fuera de Git.
- Crear el primer administrador por CLI local, sin password predeterminado ni registro abierto.
- Publicar primero la base modular y este plan; despues implementar la etapa 1.
- Cada etapa se valida antes de abrir la siguiente via de acceso.
- No alterar la instalacion activa ni las reglas de Tailscale durante la preparacion del portal.

## Referencias de red

- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
- [Compartir equipos](https://tailscale.com/docs/features/sharing)
- [Funnel y sus limites](https://tailscale.com/docs/features/tailscale-funnel)

Funnel tiene limites de ancho de banda y no puede compartir un mismo puerto con
Serve en modo privado simultaneamente. Usar entradas separadas y verificar la
documentacion al desplegar. La configuracion concreta de red no se guarda en el repo.
