# Validacion de cola y trabajador · 2026-11-27

- 49 pruebas Python del portal y trabajador: propietarios, permisos, sesiones,
  almacenamiento, cola, cuota, cancelacion, reintentos, migracion, recuperacion y
  ocultacion de resultados parciales. Los artefactos se crean en carpetas temporales.
- Siete pruebas del auditor ampliado de privacidad.
- Prueba JavaScript de cambio de sesion: una respuesta tardia del usuario anterior
  no muestra sus datos ni cierra la sesion nueva. Sintaxis JavaScript comprobada.
- Cuatro plantillas aceptadas por el validador del ComfyUI instalado: 2D, 2D con
  referencia y 3D con y sin color. Esta comprobacion no ejecuta inferencia.

No se generaron nuevos modelos con la GPU durante esta validacion: estaba ocupada
por otra carga. La prueba de inferencia real sigue pendiente antes del piloto
remoto. No se modificaron reglas de red ni se expuso ComfyUI.

## Privacidad

Se revisaron el arbol actual, los blobs historicos y los mensajes/autoria de Git.
No se detectaron credenciales, cuentas privadas, direcciones de red privadas,
telefonos ni rutas personales con las reglas actuales. Los valores encontrados
no se imprimen en los informes: solo archivo, linea y regla.

El historial conserva autoria/creditos publicos, una direccion loopback en un
mensaje antiguo y dos versiones de una nota con contacto atribuido a un proveedor.
No son claves de acceso ni datos de un cliente. El contacto se retiro de la guia
actual. No se reescribio la historia publicada. Esta distincion esta documentada
en SECURITY.md y el auditor; no se afirma anonimato completo de la cuenta GitHub.

Los modelos, referencias, sesiones, bases SQLite, configuracion privada e informes
locales no forman parte del commit. La revision estatica no certifica ausencia de
cualquier secreto posible ni sustituye las pruebas del despliegue final.
