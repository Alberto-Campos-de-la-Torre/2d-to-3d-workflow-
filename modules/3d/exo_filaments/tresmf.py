"""3MF con pintura por cara compatible con Creality Print 6.3.

La geometria debe llegar cerrada y orientada con Z arriba, en milimetros.
No contiene perfiles de temperatura ni instrucciones de movimiento.
"""
import json
import zipfile

import numpy as np


def escribir_3mf(destino, vertices, caras, etiquetas, colores):
    vertices = np.asarray(vertices)
    caras = np.asarray(caras)
    etiquetas = np.asarray(etiquetas)
    colores = np.asarray(colores)
    if not 1 <= len(colores) <= 16 or len(etiquetas) != len(caras):
        raise ValueError("Paleta o etiquetas invalidas para 3MF")
    if etiquetas.min() < 0 or etiquetas.max() >= len(colores):
        raise ValueError("Una cara apunta a un filamento inexistente")
    hexes = ['#' + ''.join(f'{int(x):02X}' for x in rgb)
             for rgb in np.rint(np.clip(colores, 0, 1) * 255)]
    # Codificacion de TriangleSelector, CONST_FILAMENTS en Model.cpp v6.3.0.
    pintura = ['4', '8'] + [f'{i:X}C' for i in range(14)]
    posiciones = vertices.copy()
    posiciones[:, 2] -= posiciones[:, 2].min()
    centro = (posiciones[:, :2].min(axis=0) + posiciones[:, :2].max(axis=0)) / 2
    posiciones[:, :2] -= centro
    cabecera = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<metadata name="BambuStudio:3mfVersion">1</metadata>'
        # El importador solo carga como proyecto nativo los prefijos reconocidos.
        # Generator conserva la atribucion real del exportador.
        '<metadata name="Application">Creality_Print V6.3.0 compatible export</metadata>'
        '<metadata name="Generator">Exo filaments</metadata>'
        '<resources><object id="1" type="model" name="pieza"><mesh><vertices>')
    partes = [cabecera]
    partes.extend(f'<vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>' for x, y, z in posiciones)
    partes.append('</vertices><triangles>')
    partes.extend(f'<triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{pintura[int(e)]}"/>'
                  for (a, b, c), e in zip(caras, etiquetas))
    partes.append('</triangles></mesh></object><object id="2" type="model" name="pieza">'
        '<components><component objectid="1"/></components></object></resources>'
        '<build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 175 175 0"/></build></model>')
    modelo = ('<?xml version="1.0" encoding="UTF-8"?><config>'
        '<object id="2"><metadata key="name" value="pieza"/>'
        '<metadata key="extruder" value="1"/><part id="1" subtype="normal_part">'
        '<metadata key="name" value="pieza"/></part></object>'
        '<plate><metadata key="plater_id" value="1"/><model_instance>'
        '<metadata key="object_id" value="2"/><metadata key="instance_id" value="0"/>'
        '</model_instance></plate></config>')
    config = {'filament_colour': hexes, 'filament_diameter': ['1.75'] * len(hexes),
              'filament_is_support': ['0'] * len(hexes),
              'filament_type': ['PLA'] * len(hexes),
              'filament_settings_id': ['Generic PLA @Creality K2 Plus 0.4 nozzle'] * len(hexes),
              'printer_settings_id': 'Creality K2 Plus 0.4 nozzle',
              'print_settings_id': '0.20mm Standard @Creality K2 Plus 0.4 nozzle'}
    with zipfile.ZipFile(destino, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model', ''.join(partes))
        z.writestr('Metadata/model_settings.config', modelo)
        z.writestr('Metadata/project_settings.config', json.dumps(config))
    return destino
