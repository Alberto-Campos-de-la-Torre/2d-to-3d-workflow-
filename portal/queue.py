"""Cola persistente y arrendamiento unico del recurso GPU dentro del portal."""
import json
import secrets
import time
import uuid
from .store_errors import ErrorPortal


class LeaseLost(RuntimeError):pass


class Queue:
    def __init__(self,store,lease_seconds=45):
        self.store=store;self.resource='gpu';self.token=secrets.token_urlsafe(24);self.ttl=lease_seconds

    def acquire(self):
        now=time.time()
        with self.store.connect() as db:
            cur=db.execute('''INSERT INTO worker_lease VALUES(?,?,?,?,?) ON CONFLICT(resource) DO UPDATE SET
                token=excluded.token,expires=excluded.expires,heartbeat=excluded.heartbeat,status=excluded.status
                WHERE worker_lease.expires<? OR worker_lease.token=?''',
                (self.resource,self.token,now+self.ttl,now,'iniciando',now,self.token))
            return bool(cur.rowcount)

    def guard(self,db):
        r=db.execute('SELECT 1 FROM worker_lease WHERE resource=? AND token=? AND expires>?',(self.resource,self.token,time.time())).fetchone()
        if not r:raise LeaseLost('El trabajador perdio el recurso; debe detenerse')

    def heartbeat(self,status='disponible'):
        now=time.time()
        with self.store.connect() as db:
            cur=db.execute('UPDATE worker_lease SET expires=?,heartbeat=?,status=? WHERE resource=? AND token=? AND expires>?',(now+self.ttl,now,status,self.resource,self.token,now))
            if not cur.rowcount:raise LeaseLost('El trabajador perdio el recurso')

    def release(self):
        with self.store.connect() as db:db.execute('DELETE FROM worker_lease WHERE resource=? AND token=?',(self.resource,self.token))

    def claim(self):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.guard(db)
            active=db.execute("SELECT id FROM jobs WHERE state IN ('preparando','enviando','ejecutando','importando','cancelacion_solicitada','requiere_revision') ORDER BY created LIMIT 1").fetchone()
            if active:return self.internal(active[0])
            db.execute("UPDATE jobs SET state='cancelado' WHERE state='pendiente' AND owner IN (SELECT id FROM users WHERE active=0)")
            job=db.execute("SELECT id FROM jobs WHERE state='pendiente' ORDER BY created,id LIMIT 1").fetchone()
            if not job:return None
            db.execute("UPDATE jobs SET state='preparando' WHERE id=?",(job[0],))
            db.execute("UPDATE job_runtime SET attempt=attempt+1,prompt_id=?,progress=0,stage='preparando',error='',started=?,submitted=0 WHERE job=?",(str(uuid.uuid4()),time.time(),job[0]))
        return self.internal(job[0])

    def internal(self,ident):
        with self.store.connect() as db:
            row=db.execute('SELECT j.*,u.active FROM jobs j JOIN users u ON u.id=j.owner WHERE j.id=?',(ident,)).fetchone()
            if not row:return None
            owner={'id':row['owner'],'role':'cliente'}
            runtime=db.execute('SELECT * FROM job_runtime WHERE job=?',(ident,)).fetchone()
        return {**self.store.job(ident,owner),'runtime':dict(runtime),'active':row['active']}

    def update(self,ident,state=None,stage=None,progress=None,error=None,submitted=None):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.guard(db)
            row=db.execute('SELECT state FROM jobs WHERE id=?',(ident,)).fetchone()
            if not row:raise LeaseLost('El trabajo ya no existe')
            if state and not (row['state']=='cancelacion_solicitada' and state not in ('cancelado','fallido','requiere_revision')):
                db.execute('UPDATE jobs SET state=? WHERE id=?',(state,ident))
            values={k:v for k,v in [('stage',stage),('progress',progress),('error',error),('submitted',submitted)] if v is not None}
            if values:
                db.execute('UPDATE job_runtime SET '+','.join(k+'=?' for k in values)+' WHERE job=?',(*values.values(),ident))

    def discard_results(self,ident):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.guard(db)
            rows=db.execute("SELECT * FROM files WHERE job=? AND type='resultado'",(ident,)).fetchall()
            for row in rows:self.store.path(dict(row)).unlink(missing_ok=True)
            db.execute("DELETE FROM files WHERE job=? AND type='resultado'",(ident,))

    def complete(self,ident):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.guard(db)
            row=db.execute('SELECT state FROM jobs WHERE id=?',(ident,)).fetchone()
            if row['state']=='cancelacion_solicitada':return False
            db.execute("UPDATE jobs SET state='terminado' WHERE id=?",(ident,))
            db.execute("UPDATE job_runtime SET stage='terminado',progress=100,error='' WHERE job=?",(ident,))
        return True


def retry(store,ident,user):
    job=store.job(ident,user)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state FROM jobs WHERE id=?',(ident,)).fetchone()[0]
        attempt=db.execute('SELECT attempt FROM job_runtime WHERE job=?',(ident,)).fetchone()[0]
        if current not in ('fallido','cancelado'):raise ErrorPortal(409,'El trabajo no admite reintento')
        if attempt>=job['opciones']['max_intentos']:raise ErrorPortal(409,'Se alcanzo el limite de intentos')
        count=db.execute("SELECT count(*) FROM jobs WHERE owner=? AND state IN ('pendiente','preparando','enviando','ejecutando','importando','cancelacion_solicitada','requiere_revision')",(job['owner'],)).fetchone()[0]
        if count>=2:raise ErrorPortal(429,'Hay dos trabajos pendientes o activos')
        db.execute("UPDATE jobs SET state='pendiente' WHERE id=?",(ident,))
        db.execute("UPDATE job_runtime SET stage='en_cola',progress=0,error='',prompt_id=NULL,submitted=0 WHERE job=?",(ident,))
    return store.job(ident,user)
