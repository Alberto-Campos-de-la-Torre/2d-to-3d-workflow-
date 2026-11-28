# Validacion de etapa 3

Fecha: 2026-11-27. Piloto privado limitado inicialmente a la identidad del
propietario del equipo, sin registro abierto ni administrador predeterminado.

## Evidencia automatizada

- 65 pruebas del portal/trabajador pasaron al integrar el filtro privado.
- Pruebas adicionales de despliegue y cabeceras duplicadas documentadas en
  `portal/tests/test_private_access.py`: 20 pruebas del filtro/despliegue pasaron.
  Junto a las 49 pruebas previas del portal/trabajador, cubren 69 casos diferentes.
- Rechazo de identidad ausente/ajena, Host/Origin incorrectos, configuracion rota
  o eliminada y cambios de origen sin reinicio.
- Revocacion de identidad sin reiniciar; roles de aplicacion independientes de red.
- Cookie Secure y HttpOnly; bloqueo de configuracion privada con cookies inseguras.
- Conflictos de puerto y retirada de ruta ajena rechazados sin reset global.

## Comprobaciones reales en el servidor

Se inicio el portal en loopback y se publico con un puerto Serve HTTPS separado
del servicio ya existente. Los datos reales de red y los resultados detallados
quedaron fuera del checkout, en el directorio privado de datos del usuario.

| Prueba | Resultado |
| --- | --- |
| Pagina por HTTPS privado, certificado validado | 200 |
| API de usuario sin sesion del portal | 401 |
| Ruta bruta `/prompt` | 404 |
| Origen de otro sitio | 403 |
| Cabecera de identidad falsa enviada al proxy | Eliminada por Serve; se uso la identidad real |
| Backend local sin identidad | 403 |
| Configuracion TCP/Web de servicios previos | Conservada |
| Funnel | Desactivado |

No se crearon cuentas reales ni se enviaron invitaciones. El alta inicial se
realiza por CLI local con contrasena elegida por el propietario. No se ejecutaron
inferencias GPU en esta etapa. El trabajador sigue siendo un proceso separado.

## Limites pendientes de aceptacion

La prueba desde el propio servidor no acredita acceso desde un celular o un equipo
invitado. Se consulto en memoria el filtro efectivo local mediante el diagnostico
de Tailscale, sin imprimir direcciones, identidades ni claves. Contiene una regla
con destino comodin y todos los puertos para sus origenes autorizados: no permite
dar por acreditado aislamiento al puerto del portal. No se obtuvo ni modifico la
politica global: la lista de identidad del portal protege solo esta aplicacion.
Antes de compartir el equipo se deben revisar grants/ACL y ejecutar pruebas
negativas desde la identidad invitada. No se ampliaron identidades autorizadas.

El portal se inicia como proceso oculto para el piloto, sin arranque automatico
del sistema. Reiniciar la PC exige volver a iniciarlo. Si Serve permanece activo
y el proceso esta detenido, no habra backend disponible; no se publicara otro servicio.

La auditoria de entrega revisa archivos e historial sin imprimir secretos. Las
atribuciones publicas y dos blobs historicos con un contacto de proveedor siguen
siendo antecedentes documentados; no se reescribio el historial para esta etapa.
