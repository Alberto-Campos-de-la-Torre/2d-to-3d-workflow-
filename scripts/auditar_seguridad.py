"""Auditoria sin imprimir valores de secretos ni datos personales."""
import argparse,ipaddress,json,re,subprocess
from pathlib import Path

RULES={
 'correo_no_ejemplo':re.compile(r'\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b'),
 'host_privado':re.compile(r'https?://[^/\s"\']+\.(?:ts\.net|local)(?=[:/\s"\']|$)'),
 'contacto_telefonico':re.compile(r'(?:tel:|wa\.me/)[+0-9]{7,}'),
 'conexion_autenticada':re.compile(r'(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^\s/:]+:[^\s/@]+@'),
 'ruta_usuario_unix':re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+/'),
 'clave_almacenamiento':re.compile(r'(?i)(?:AccountKey|SharedAccessSignature)=[A-Za-z0-9+/=]{20,}'),
 'clave_proveedor':re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|hf_[A-Za-z0-9]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16})\b'),
 'llave_privada':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 'credencial_literal':re.compile(r'''(?i)(?:api[_-]?key|password|passwd|secret|authorization)\s*["']?\s*[:=]\s*["']([^"'\s]{12,})["']'''),
 'correo_personal':re.compile(r'\b[A-Za-z0-9._%+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.[A-Za-z]{2,}\b'),
 'ruta_personal':re.compile(r'(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s"\']+'),
 'ip':re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])'),
 'jwt':re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'),
 'url_autenticada':re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
 'bearer_literal':re.compile(r'\bBearer[ \t]+[A-Za-z0-9._-]{20,}'),
 'secreto_en_query':re.compile(r'(?i)[?&](?:api_key|access_token|token|secret)=[A-Za-z0-9._-]{16,}'),
}
BLOCKED={'.png','.jpg','.jpeg','.webp','.stl','.obj','.mtl','.glb','.gltf','.3mf','.ply','.safetensors','.ckpt','.gguf','.pt','.pth','.bin','.zip','.7z','.exe','.pyc'}
def scan(name,data,attribution=False):
    findings=[]
    for line,text in enumerate(data.decode('utf-8',errors='replace').splitlines(),1):
        for rule,rx in RULES.items():
            for m in rx.finditer(text):
                severity='error'
                if rule=='correo_no_ejemplo':
                    domain=m.group(1).lower();local=m.group().split('@')[0].lower()
                    if domain.endswith('.invalid') or domain in ('example.com','example.org','example.net'):continue
                    if attribution and (domain=='users.noreply.github.com' or (domain=='anthropic.com' and local=='noreply')):
                        severity='info'
                if rule=='ip':
                    try:ip=ipaddress.ip_address(m.group())
                    except ValueError:continue
                    severity='info' if ip.is_loopback or ip.is_unspecified else 'error'
                if rule=='credencial_literal' and any(s in m.group(1).lower() for s in ('example','placeholder','changeme','your_','your-','<','${')):continue
                findings.append({'archivo':name,'linea':line,'regla':rule,'nivel':severity})
    return findings
def audit(repo,history=False):
    findings=[];files=0;total=0
    for p in repo.rglob('*'):
        if not p.is_file() or any(x in p.parts for x in ('.git','__pycache__','.venv','venv')):continue
        name=p.relative_to(repo).as_posix();files+=1;total+=p.stat().st_size
        if p.suffix.lower() in BLOCKED or p.stat().st_size>2*1024*1024:
            findings.append({'archivo':name,'regla':'archivo_no_publicable','nivel':'error'})
        if p.name in ('config_local.json','.env','revisiones.json','catalogo.json','acceso-privado.json','serve-anterior.json','serve-piloto.json','ABRIR_PORTAL.txt','validacion-privada.json','portal-proceso.json'):
            findings.append({'archivo':name,'regla':'datos_locales','nivel':'error'})
        findings+=scan(name,p.read_bytes())
    metadata=[]
    if history:
        objects=subprocess.check_output(['git','-C',str(repo),'rev-list','--objects','--all'],text=True).splitlines()
        for entry in objects:
            oid,_,name=entry.partition(' ')
            if not name:continue
            kind=subprocess.check_output(['git','-C',str(repo),'cat-file','-t',oid],text=True).strip()
            if kind!='blob':continue
            if Path(name).suffix.lower() in BLOCKED:
                findings.append({'archivo':name,'objeto':oid,'regla':'archivo_no_publicable_en_historial','nivel':'error'})
            data=subprocess.check_output(['git','-C',str(repo),'cat-file','blob',oid])
            for f in scan(name,data):
                # Dos versiones historicas de una nota con contacto de proveedor;
                # se conserva la trazabilidad sin introducir ese correo en codigo nuevo.
                if f['regla']=='correo_no_ejemplo' and oid in {'c4affbd6c25781efce18afc603046414bb0c4de9','ee7494526d9862c93bf03a88acdd0a54a372a886'}:
                    f['nivel']='info'
                if f['nivel']=='error':f['objeto']=oid;findings.append(f)
                elif f['regla']=='correo_no_ejemplo':f['objeto']=oid;findings.append(f)
        log=subprocess.check_output(['git','-C',str(repo),'log','--all','--format=%H%x09%ae%x09%ce'],text=True)
        for row in log.splitlines():
            parts=row.split('\t')
            if any(RULES['correo_personal'].search(s) for s in parts[1:]):metadata.append({'commit':parts[0],'regla':'correo_personal_en_autoria'})
        messages=subprocess.check_output(['git','-C',str(repo),'log','--all','--format=%H%n%an <%ae>%n%cn <%ce>%n%B'])
        findings+=scan('metadata_y_mensajes_git',messages,attribution=True)
    return {'archivos':files,'bytes':total,'hallazgos':findings,'autoria':metadata,'errores':sum(f['nivel']=='error' for f in findings)+len(metadata)}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('repo',type=Path);ap.add_argument('--historial',action='store_true');ap.add_argument('--informe',type=Path,required=True)
    args=ap.parse_args();r=audit(args.repo,args.historial);args.informe.write_text(json.dumps(r,indent=2),encoding='utf-8')
    print(json.dumps({'archivos':r['archivos'],'bytes':r['bytes'],'errores':r['errores'],'hallazgos_por_regla':{k:sum(f['regla']==k for f in r['hallazgos']) for k in RULES},'autoria':len(r['autoria'])}))
    raise SystemExit(1 if r['errores'] else 0)
