# Revision antes de compartir

## Alcance de la entrega (2026-11-26)

Revisados los archivos publicables, el historial Git local y la autoria de los commits.
Se buscan claves de proveedores, llaves privadas, credenciales literales, tokens JWT,
URLs autenticadas, correos personales, rutas personales e IP de red.
Los informes de hallazgos detallados se mantienen fuera de este repositorio; el
escaneo informa archivo y linea sin imprimir el valor encontrado.

La copia compartida excluye modelos, pesos, fotos, resultados, referencias de
clientes, pedidos, registros locales, catalogos y configuracion privada. Los modelos
solo se mencionan por nombre o URL de descarga. No se descargan al instalar el codigo.
Las configuraciones de ejemplo son publicas y deben sustituirse en cada instalacion.

```powershell
python scripts/auditar_seguridad.py . --historial --informe <ruta-privada-del-informe>
```

El resultado sin hallazgos es una comprobacion estatica con patrones, no una garantia
de ausencia de cualquier secreto posible. Antes de publicar verifica tambien
`git diff --cached`, archivos nuevos y la configuracion de tu remoto.

## Datos locales

No versionar `.env`, `config_local.json`, `input/`, `output/`, `user/`, `encargos/`,
copias de seguridad ni archivos de modelos. `.gitignore` ayuda a excluirlos, pero
no elimina un secreto que ya se haya confirmado en Git. Si descubres una credencial
publicada, revocala y revisa el historial antes de volver a compartir.

## Red y borrado

ComfyUI no incorpora autenticacion en este proyecto. El inicio LAN debe limitarse
a una red de confianza; no exponerlo directamente a Internet. Los endpoints de
borrado afectan archivos reales y requieren confirmacion de su alcance. Referencias
compartidas se conservan mientras otros resultados las utilicen.

## Instalacion modular

El perfil 2D no importa motores ni librerias de mallas. El perfil 3D no requiere
la instalacion de Qwen ni del Estudio. Ambos incluyen utilidades comunes, y el perfil
`ambos` habilita su conexion. El paquete anterior se conserva para compatibilidad;
el instalador nuevo usa exclusivamente los directorios `modules/` e `integration/`.


## Comprobacion ampliada de privacidad (2026-11-27)

El auditor tambien revisa correos de cualquier dominio, hosts de tailnet, contactos
telefonicos estructurados, rutas personales Unix, conexiones autenticadas y mensajes
de commit. No se encontraron cuentas privadas o credenciales en esta entrega.

La autoria de GitHub y creditos de coautoria publicos siguen siendo visibles en Git.
Dos blobs historicos de una nota contienen un contacto atribuido a un proveedor;
se clasifican como referencia documental publica por su hash exacto, no mediante
una excepcion para futuros correos. El contacto se retiro del archivo actual.
Esta revision no reescribe ni anonimiza el historial ya publicado. Los informes
distinguen estas menciones informativas de datos privados; no son claves de acceso.

El trabajador solo usa ComfyUI local y directorios por intento. Rechaza rutas de
resultados ajenas, no importa PNG con su metadata original y no publica resultados
parciales. La reserva de GPU evita trabajadores simultaneos dentro del mismo portal.
El acceso por Tailscale o Internet requiere las etapas posteriores del plan.
