# Etapa 3: piloto privado

El portal se publica con Tailscale Serve. No publicar ComfyUI ni el LLM. El perfil
privado exige tanto identidad de red autorizada como cuenta y permisos del portal.
Funnel y el acceso para visitantes sin Tailscale corresponden a otra etapa.

## Preparar

Instalar los requisitos de `portal/requirements.txt`. Con Python convencional se
puede usar `python -m portal`; con una distribucion embebida usar el lanzador:

```powershell
python scripts/portal_cli.py preparar-piloto --puerto-https 10000 --puerto-local 8090
python scripts/portal_cli.py crear-usuario <usuario-elegido> --rol administrador
```

La contrasena se solicita en la consola sin mostrarse. No existe contrasena
predeterminada, registro publico ni cuenta administradora automatica. No introducir
contrasenas en argumentos ni en archivos versionados.
Si se omite el nombre de usuario, tambien se solicita interactivamente.

Preparar consulta el equipo personal conectado y autoriza inicialmente solo a su
propietario. Rechaza puertos ocupados y directorios de datos dentro de Git. Los
datos privados se guardan en `.exo-portal` del directorio personal o en `--datos`.
Incluyen `acceso-privado.json` y una copia de la configuracion previa de Serve.
No copiar esos archivos al repositorio. El directorio personal y la PC deben estar
protegidos por los permisos del sistema: otros procesos locales del servidor
pertenecen al limite de confianza.
Los servicios con el mismo hostname comparten el ambito de cookies aunque usen
puertos distintos. Alojar solo aplicaciones de confianza en ese hostname; separar
dominios/hosts antes de alojar servicios de terceros no confiables.

## Iniciar y publicar

```powershell
python scripts/portal_cli.py servir --acceso-privado <directorio-privado>/acceso-privado.json
```

Dejar ese proceso activo y, en otra consola:

```powershell
python scripts/portal_cli.py publicar-piloto
```

Usar el mismo `--datos` en todos los comandos si se cambia el directorio. Si se
eligio otro puerto local, pasarlo tambien con `servir --puerto`. El perfil privado
solo admite `--host localhost` y cookies Secure; no combinarlo con `--local-http`.
El enlace se escribe en `ABRIR_PORTAL.txt` dentro del directorio privado. No imprimir
ni publicar la configuracion completa en incidencias de GitHub.

Publicar comprueba que el backend rechaza solicitudes sin identidad, reserva un
puerto HTTPS independiente y verifica la ruta. No ejecuta Serve reset, Funnel,
reglas de firewall ni modificaciones de politica de red. Conserva otros servicios.
Rechaza volver a publicar sobre un puerto ocupado, incluso si parece propio.

Para retirar solo la publicacion registrada de este piloto:

```powershell
python scripts/portal_cli.py retirar-piloto
```

Se niega a eliminarla si alguien cambio la ruta despues. No detiene el portal ni
otros servicios. Para reiniciar el portal hay que iniciar su proceso otra vez; esta
etapa no instala arranque automatico ni un servicio de Windows.

## Autorizar y revocar

Editar localmente `identidades_permitidas` en `acceso-privado.json`, usando los
logins exactos de Tailscale. Guardar de forma atomica cuando sea posible. La lista
se relee en cada solicitud; una lista vacia, archivo ausente o JSON invalido cierra
el acceso. Cambiar `origen` requiere reiniciar. Las identidades se comparan sin
distincion de mayusculas y admiten la codificacion de cabeceras documentada.

La identidad de Serve no crea cuentas, no inicia sesion y no otorga administracion.
Los equipos etiquetados sin identidad personal son rechazados. No se confia en
X-Forwarded-For. Host y Origin se contrastan con el origen HTTPS configurado.
Una revocacion bloquea nuevas peticiones de esa identidad, tambien con sesion
iniciada; no cancela automaticamente los trabajos ya aceptados.

## Antes de invitar a otra persona

La lista del portal protege esta aplicacion. No restringe el acceso de red a otros
puertos del equipo ni sustituye las ACL/grants de la tailnet. Revisar la politica
vigente y eliminar permisos amplios que alcancen el servidor: una regla mas
restrictiva no revoca permisos otorgados por otra regla. No modificar a ciegas la
politica global cuando se alojan otros proyectos en el mismo equipo.

Para una persona de otra tailnet, compartir solo este equipo y limitar su acceso
al puerto HTTPS del portal. Crear su cuenta de cliente desde el administrador y
agregar su identidad localmente. Comprobar desde su equipo o celular que el portal
funciona y que ComfyUI, LLM y otros servicios no son alcanzables. Revocar identidad
y cuenta y volver a probar. No se enviaron invitaciones como parte de esta entrega.

En celular, conectar Tailscale, abrir el enlace HTTPS privado y probar login,
referencia desde galeria/camara, trabajo, progreso, descarga y borrado. La prueba
en el propio servidor no acredita compatibilidad de navegador ni aislamiento
desde otro dispositivo. Probar tambien con Tailscale desconectado.

El trabajador de la etapa 2 sigue siendo un proceso separado. El portal informa
cuando esta desconectado. No iniciar inferencia si otros procesos ya ocupan la GPU.

## Validacion de esta entrega

Pruebas automatizadas del filtro: identidad ausente/ajena, host/origen incorrectos,
revocacion, configuracion rota, cookies seguras, roles separados y ausencia de API
general del motor. Pruebas de despliegue: conflictos y retirada de rutas ajenas.
La comprobacion real del despliegue se detalla en `VALIDACION_ETAPA3.md`.

Fuentes oficiales:

- [Serve y cabeceras de identidad](https://tailscale.com/docs/features/tailscale-serve)
- [Comandos y retirada de una ruta Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Politicas de acceso](https://tailscale.com/docs/features/access-control)
- [Compartir un equipo](https://tailscale.com/docs/features/sharing)
