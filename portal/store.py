import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

ROLES={'administrador','operador','cliente'}


class ErrorPortal(Exception):
    def __init__(self,status,mensaje):
        super().__init__(mensaje);self.status=status


def password_hash(password):
    if not isinstance(password,str) or len(password)<12 or len(password.encode())>1024:
        raise ErrorPortal(400,'La contraseña debe tener al menos 12 caracteres y hasta 1024 bytes')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,maxmem=64*1024*1024)
    return 'scrypt$32768$8$1$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(digest).decode()


def password_ok(password,encoded):
    if not isinstance(password,str) or len(password.encode())>1024:return False
    _,n,r,p,salt,expected=encoded.split('$')
    got=hashlib.scrypt(password.encode(),salt=base64.b64decode(salt),n=int(n),r=int(r),p=int(p),maxmem=64*1024*1024)
    return hmac.compare_digest(got,base64.b64decode(expected))


def token_hash(value):return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self,root,session_seconds=43200):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'portal.sqlite3';self.session_seconds=session_seconds
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(
              id TEXT PRIMARY KEY, login TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('administrador','operador','cliente')),
              active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
              hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
              prompt TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
              request_id TEXT NOT NULL, signature TEXT NOT NULL, UNIQUE(owner,request_id));
            CREATE TABLE IF NOT EXISTS files(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
              job TEXT REFERENCES jobs(id) ON DELETE CASCADE, type TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE, mime TEXT NOT NULL, size INTEGER NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS job_refs(
              job TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
              file TEXT NOT NULL REFERENCES files(id), PRIMARY KEY(job,file));
            ''')
        # Evita una diferencia extrema de coste entre login inexistente y contraseña incorrecta.
        self.dummy=password_hash(secrets.token_urlsafe(24))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=5);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()

    def create_user(self,login,password,role='cliente'):
        if not isinstance(login,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,64}',login):
            raise ErrorPortal(400,'Nombre de usuario: 3 a 64 letras, numeros, puntos, guiones o guiones bajos')
        if not isinstance(role,str) or role not in ROLES:raise ErrorPortal(400,'Rol invalido')
        encoded=password_hash(password);ident=uuid.uuid4().hex
        try:
            with self.connect() as db:db.execute('INSERT INTO users VALUES(?,?,?,?,1,?)',(ident,login.lower(),encoded,role,time.time()))
        except sqlite3.IntegrityError:raise ErrorPortal(409,'Ese nombre de usuario ya existe')
        return {'id':ident,'login':login.lower(),'role':role}

    def login(self,login,password,remote):
        if not isinstance(login,str) or len(login)>64:raise ErrorPortal(401,'Credenciales invalidas')
        now=time.time();key=token_hash(login.lower()+'|'+remote)
        with self.connect() as db:
            attempt=db.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
            if attempt and attempt['failures']>=5 and attempt['until']>now:
                raise ErrorPortal(429,'Demasiados intentos; espera unos minutos')
            user=db.execute('SELECT * FROM users WHERE login=?',(login.lower(),)).fetchone()
        valid=password_ok(password,user['password'] if user else self.dummy)
        if not valid or not user or not user['active']:
            with self.connect() as db:
                failures=(attempt['failures'] if attempt and attempt['until']>now else 0)+1
                db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,failures,now+900))
            raise ErrorPortal(401,'Credenciales invalidas')
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM attempts WHERE key=?',(key,))
            db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token_hash(token),user['id'],csrf,now+self.session_seconds))
        return token,{'id':user['id'],'login':user['login'],'role':user['role'],'csrf':csrf}

    def session(self,token):
        if not token or len(token)>128:return None
        with self.connect() as db:
            row=db.execute('SELECT u.id,u.login,u.role,s.csrf FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.hash=? AND s.expires>? AND u.active=1',(token_hash(token),time.time())).fetchone()
        return dict(row) if row else None

    def logout(self,token):
        with self.connect() as db:db.execute('DELETE FROM sessions WHERE hash=?',(token_hash(token),))

    def users(self):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT id,login,role,active FROM users ORDER BY login')]

    def set_active(self,ident,active):
        if not isinstance(active,bool):raise ErrorPortal(400,'activo debe ser booleano')
        with self.connect() as db:
            user=db.execute('SELECT * FROM users WHERE id=?',(ident,)).fetchone()
            if not user:raise ErrorPortal(404,'Usuario no encontrado')
            if not active and user['active'] and user['role']=='administrador':
                count=db.execute("SELECT count(*) FROM users WHERE active=1 AND role='administrador'").fetchone()[0]
                if count<=1:raise ErrorPortal(409,'Debe quedar al menos un administrador activo')
            db.execute('UPDATE users SET active=? WHERE id=?',(active,ident))
            if not active:db.execute('DELETE FROM sessions WHERE user_id=?',(ident,))

    @staticmethod
    def owned(row,user):
        if not row or (row['owner']!=user['id'] and user['role']!='administrador'):
            raise ErrorPortal(404,'Recurso no encontrado')
        return dict(row)

    def path(self,row):
        allowed=(self.root/'usuarios'/row['owner']).resolve()
        path=(self.root/row['path']).resolve()
        if not allowed.is_relative_to(self.root) or not path.is_relative_to(allowed):
            raise ErrorPortal(404,'Archivo no disponible')
        return path

    def save_file(self,owner,data,mime,kind='referencia',job=None):
        suffix={'image/png':'.png','model/gltf-binary':'.glb','model/stl':'.stl','model/3mf':'.3mf'}.get(mime)
        if not suffix:raise ErrorPortal(400,'Formato no permitido')
        ident=uuid.uuid4().hex
        row={'id':ident,'owner':owner,'job':job,'type':kind,'path':f'usuarios/{owner}/{ident}{suffix}',
             'mime':mime,'size':len(data),'created':time.time()}
        path=self.path(row);path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            if job:
                record=db.execute('SELECT owner FROM jobs WHERE id=?',(job,)).fetchone()
                if not record or record['owner']!=owner:raise ErrorPortal(404,'Trabajo no encontrado')
            path.write_bytes(data)
            try:db.execute('INSERT INTO files VALUES(:id,:owner,:job,:type,:path,:mime,:size,:created)',row)
            except Exception:
                path.unlink(missing_ok=True);raise
        return {k:v for k,v in row.items() if k!='path'}

    def file(self,ident,user):
        with self.connect() as db:row=db.execute('SELECT * FROM files WHERE id=?',(ident,)).fetchone()
        return self.owned(row,user)

    def files(self,user):
        with self.connect() as db:
            rows=db.execute('SELECT id,owner,job,type,mime,size,created FROM files'+('' if user['role']=='administrador' else ' WHERE owner=?')+' ORDER BY created DESC',() if user['role']=='administrador' else (user['id'],))
            return [dict(r) for r in rows]

    def delete_file(self,ident,user):
        with self.connect() as db:
            row=self.owned(db.execute('SELECT * FROM files WHERE id=?',(ident,)).fetchone(),user)
            if db.execute('SELECT 1 FROM job_refs WHERE file=?',(ident,)).fetchone():raise ErrorPortal(409,'La referencia sigue vinculada a un trabajo')
            if row['job']:raise ErrorPortal(409,'Borra el trabajo para eliminar sus resultados')
            self.path(row).unlink(missing_ok=True)
            db.execute('DELETE FROM files WHERE id=?',(ident,))

    def create_job(self,user,body):
        if not isinstance(body,dict) or set(body)-{'tipo','prompt','referencias','request_id'}:
            raise ErrorPortal(400,'Solicitud invalida: no se aceptan grafos, rutas ni propietarios enviados por el cliente')
        kind=body.get('tipo');prompt=body.get('prompt','');refs=body.get('referencias',[])
        request_id=body.get('request_id') or uuid.uuid4().hex
        if kind not in ('2d','3d') or not isinstance(prompt,str) or len(prompt)>4000:
            raise ErrorPortal(400,'Tipo o prompt invalido')
        if not isinstance(refs,list) or len(refs)>16 or any(not isinstance(i,str) for i in refs) or len(set(refs))!=len(refs):
            raise ErrorPortal(400,'Referencias invalidas')
        if kind=='3d' and len(refs)!=1:raise ErrorPortal(400,'El trabajo 3D necesita una imagen de referencia')
        if kind=='2d' and not prompt.strip():raise ErrorPortal(400,'Escribe lo que quieres generar')
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',request_id):raise ErrorPortal(400,'Identificador de solicitud invalido')
        signature=token_hash(json.dumps([kind,prompt,refs],sort_keys=True))
        ident=uuid.uuid4().hex
        with self.connect() as db:
            old=db.execute('SELECT * FROM jobs WHERE owner=? AND request_id=?',(user['id'],request_id)).fetchone()
            if old:
                if old['signature']!=signature:raise ErrorPortal(409,'Ese identificador ya se uso para otra solicitud')
                return self.job(old['id'],user)
            for ref in refs:
                row=db.execute("SELECT * FROM files WHERE id=? AND type='referencia'",(ref,)).fetchone()
                # Ni administradores pueden mezclar silenciosamente datos de propietarios distintos.
                if not row or row['owner']!=user['id']:raise ErrorPortal(404,'Referencia no encontrada')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(ident,user['id'],kind,prompt,'pendiente_de_motor',time.time(),request_id,signature))
            for ref in refs:db.execute('INSERT INTO job_refs VALUES(?,?)',(ident,ref))
        return self.job(ident,user)

    def job(self,ident,user):
        with self.connect() as db:
            row=self.owned(db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone(),user)
            row['referencias']=[r[0] for r in db.execute('SELECT file FROM job_refs WHERE job=?',(ident,))]
            row['resultados']=[r[0] for r in db.execute('SELECT id FROM files WHERE job=?',(ident,))]
        row.pop('signature');return row

    def jobs(self,user):
        with self.connect() as db:
            rows=db.execute('SELECT id FROM jobs'+('' if user['role']=='administrador' else ' WHERE owner=?')+' ORDER BY created DESC',() if user['role']=='administrador' else (user['id'],)).fetchall()
        return [self.job(row[0],user) for row in rows]

    def cancel(self,ident,user):
        self.job(ident,user)
        with self.connect() as db:
            cursor=db.execute("UPDATE jobs SET state='cancelado' WHERE id=? AND state='pendiente_de_motor'",(ident,))
            if not cursor.rowcount:raise ErrorPortal(409,'Este trabajo ya no puede cancelarse')
        return self.job(ident,user)

    def delete_job(self,ident,user):
        self.job(ident,user)
        with self.connect() as db:
            job=self.owned(db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone(),user)
            if job['state'] not in ('pendiente_de_motor','cancelado','terminado','fallido'):
                raise ErrorPortal(409,'Espera a que el trabajo deje de ejecutarse')
            refs=db.execute('SELECT file FROM job_refs WHERE job=?',(ident,)).fetchall()
            files=[dict(r) for r in db.execute('SELECT * FROM files WHERE job=?',(ident,))]
            for ref in refs:
                count=db.execute('SELECT count(*) FROM job_refs WHERE file=? AND job<>?',(ref[0],ident)).fetchone()[0]
                if not count:files.append(dict(db.execute('SELECT * FROM files WHERE id=?',(ref[0],)).fetchone()))
            for row in files:self.path(row).unlink(missing_ok=True)
            db.execute('DELETE FROM job_refs WHERE job=?',(ident,))
            for row in files:db.execute('DELETE FROM files WHERE id=?',(row['id'],))
            db.execute('DELETE FROM jobs WHERE id=?',(ident,))
        return {'archivos_eliminados':len(files),'trabajo_eliminado':ident}
