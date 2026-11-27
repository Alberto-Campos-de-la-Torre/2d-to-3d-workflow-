"""Limites de recursos del portal; nunca admite nodos, rutas ni nombres de modelos."""
from .store_errors import ErrorPortal


def validate_options(kind,raw):
    if raw is None:raw={}
    if not isinstance(raw,dict):raise ErrorPortal(400,'Opciones invalidas')
    common={'semilla':None,'pasos':20,'max_intentos':2}
    extra={'resolucion':1024,'negativo':''} if kind=='2d' else {'altura_mm':80,'color':True,'resolucion_forma':1024,'resolucion_reparacion':384,'filamentos':4,'paleta':''}
    defaults={**common,**extra}
    if set(raw)-set(defaults):raise ErrorPortal(400,'Opcion no permitida')
    values={**defaults,**raw}
    for key,minimum,maximum in [('pasos',8,30),('max_intentos',1,3)]:
        if type(values[key]) is not int or not minimum<=values[key]<=maximum:raise ErrorPortal(400,'Opcion fuera de los limites del servicio: '+key)
    if values['semilla'] is not None and (type(values['semilla']) is not int or not 0<=values['semilla']<2**32-3):raise ErrorPortal(400,'Semilla invalida')
    if kind=='2d':
        if type(values['resolucion']) is not int or values['resolucion'] not in (512,768,1024):raise ErrorPortal(400,'Resolucion no permitida')
        if not isinstance(values['negativo'],str) or len(values['negativo'])>3000:raise ErrorPortal(400,'Negativo invalido')
    else:
        if type(values['altura_mm']) not in (int,float) or not 10<=values['altura_mm']<=350:raise ErrorPortal(400,'Altura no permitida')
        if not isinstance(values['color'],bool):raise ErrorPortal(400,'Color debe ser booleano')
        if values['resolucion_forma'] not in (1024,1536) or type(values['resolucion_forma']) is not int:raise ErrorPortal(400,'Resolucion de forma no permitida')
        if values['resolucion_reparacion'] not in (256,384,448,512) or type(values['resolucion_reparacion']) is not int:raise ErrorPortal(400,'Resolucion de reparacion no permitida')
        if type(values['filamentos']) is not int or not 1<=values['filamentos']<=16:raise ErrorPortal(400,'Numero de filamentos invalido')
        import re
        palette=values['paleta']
        if not isinstance(palette,str):raise ErrorPortal(400,'Paleta invalida')
        colors=[c.strip().lower() for c in palette.split(',') if c.strip()]
        if len(colors)>values['filamentos'] or any(not re.fullmatch(r'#[0-9a-f]{6}',c) for c in colors):raise ErrorPortal(400,'Paleta incompatible con los filamentos')
        values['paleta']=','.join(colors)
    return values
