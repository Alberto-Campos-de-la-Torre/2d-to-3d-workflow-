"""Instala un perfil de Exo sin modelos, sin datos y sin ejecutar pip."""
import argparse,json,shutil
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def preparar(perfil):
    modulos=('2d','3d') if perfil=='ambos' else (perfil,)
    archivos={}
    for modulo in ('common',*modulos):
        base=ROOT/'modules'/modulo/'exo_filaments'
        for p in base.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                rel=p.relative_to(base)
                if rel.name=='requirements.txt':continue
                archivos[rel]=p.read_bytes()
    archivos[Path('perfil.py')]=('MODULOS = '+repr(modulos)+'\n').encode()
    archivos[Path('perfil.json')]=json.dumps({'modulos':list(modulos)},indent=2).encode()
    requisitos=[]
    for modulo in ('common',*modulos):
        p=ROOT/'modules'/modulo/'requirements.txt'
        if p.exists():requisitos.extend(p.read_text().splitlines())
    archivos[Path('requirements.txt')]=('\n'.join(dict.fromkeys(requisitos))+'\n').encode()
    return modulos,archivos

def instalar(comfyui,perfil,actualizar=False):
    comfyui=Path(comfyui).resolve()
    if not (comfyui/'main.py').is_file():raise ValueError('Indica la carpeta ComfyUI que contiene main.py')
    modulos,archivos=preparar(perfil)
    destino=comfyui/'custom_nodes/exo_filaments'
    if destino.exists():
        if not actualizar:raise ValueError('Ya existe exo_filaments; usa otra instalacion o --actualizar con ComfyUI detenido')
        config=destino/'perfil.json'
        if config.exists():
            anteriores=set(json.loads(config.read_text())['modulos'])
            if not anteriores.issubset(modulos):
                raise ValueError('Para retirar modulos utiliza una instalacion nueva; esta actualizacion solo permite conservarlos o añadirlos')
        backup=comfyui/'user/default/exo_backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        shutil.copytree(destino,backup)
    destino.mkdir(parents=True,exist_ok=True)
    for rel,data in archivos.items():
        p=destino/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    workflows=comfyui/'user/default/workflows';workflows.mkdir(parents=True,exist_ok=True)
    carpetas=[ROOT/'modules'/m/'workflows' for m in modulos]
    if len(modulos)==2:carpetas.append(ROOT/'integration/workflows')
    for base in carpetas:
        for p in base.glob('*.json'):shutil.copy2(p,workflows/p.name)
    return destino

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--comfyui',required=True,type=Path)
    ap.add_argument('--perfil',required=True,choices=('2d','3d','ambos'))
    ap.add_argument('--actualizar',action='store_true')
    args=ap.parse_args()
    print(instalar(args.comfyui,args.perfil,args.actualizar))

if __name__=='__main__':main()
