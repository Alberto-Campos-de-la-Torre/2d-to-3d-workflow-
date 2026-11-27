import asyncio
import time

import aiohttp

from .backend import Backend,MotorError
from .queue import Queue,LeaseLost
from .store import Store
from .templates import build


class Worker:
    def __init__(self,store,backend,max_seconds=1800,poll=2):
        self.store=store;self.backend=backend;self.queue=Queue(store)
        self.max_seconds=max_seconds;self.poll=poll;self.status='iniciando';self.online=True

    async def heartbeat(self):
        while True:
            self.queue.heartbeat(self.status);await asyncio.sleep(5)

    async def finish(self,job,state,error=''):
        await self.backend.clean(job)
        self.queue.update(job['id'],state=state,stage=state,error=error,progress=100 if state=='terminado' else 0)

    async def tick(self):
        native_queue=await self.backend.queue()
        running={r[1] for r in native_queue.get('queue_running',[])}
        pending={r[1] for r in native_queue.get('queue_pending',[])}
        # No reservar un trabajo nuevo mientras un operador ya utiliza ComfyUI.
        with self.store.connect() as db:
            active=db.execute("SELECT 1 FROM jobs WHERE state IN ('preparando','enviando','ejecutando','importando','cancelacion_solicitada','requiere_revision') LIMIT 1").fetchone()
        if not active and (running or pending):self.status='motor_ocupado';return
        job=self.queue.claim()
        if not job:self.status='disponible';return
        self.status=job['state'];pid=job['runtime']['prompt_id'];ident=job['id']
        if not job['active'] and job['state']!='cancelacion_solicitada':
            self.queue.update(ident,state='cancelacion_solicitada',stage='cancelando')
            job=self.queue.internal(ident)
        if job['runtime']['stage']=='importado':
            if job['state']=='cancelacion_solicitada':
                self.queue.discard_results(ident);await self.finish(job,'cancelado');return
            await self.backend.clean(job)
            if not self.queue.complete(ident):
                self.queue.discard_results(ident);self.queue.update(ident,state='cancelado',stage='cancelado')
            return
        if job['state']=='preparando' and not job['runtime']['submitted']:
            try:
                refs,prefix=self.backend.prepare(self.store,job)
                graph=build(job,refs,prefix)
            except (OSError,ValueError,KeyError):
                await self.finish(job,'fallido','preparacion_fallida');return
            if self.queue.internal(ident)['state']=='cancelacion_solicitada':await self.finish(job,'cancelado');return
            self.queue.update(ident,state='enviando',stage='enviando',progress=10,submitted=1)
            try:await self.backend.submit(graph,pid)
            except MotorError as exc:
                if exc.code=='motor_no_admite_identificadores_estables':
                    self.queue.update(ident,state='requiere_revision',stage='requiere_revision',error=exc.code);return
                await self.finish(job,'fallido',exc.code);return
            # Si se pierde la respuesta, el UUID ya esta guardado: el siguiente ciclo reconcilia.
            self.queue.update(ident,state='ejecutando',stage='esperando_motor',progress=20)
            return
        history=await self.backend.history(pid)
        if pid in running or pid in pending:
            if job['state']=='requiere_revision':self.queue.update(ident,state='ejecutando',stage='recuperado',error='')
            expired=job['runtime']['started'] and time.time()-job['runtime']['started']>self.max_seconds
            if job['state']=='cancelacion_solicitada' or expired:
                self.queue.update(ident,state='cancelacion_solicitada',stage='cancelando',error='tiempo_agotado' if expired else '')
                await self.backend.cancel(pid)
            else:self.queue.update(ident,state='ejecutando',stage='generando' if pid in running else 'esperando_motor',progress=45 if pid in running else 20)
            return
        if history:
            if job['state']=='cancelacion_solicitada':
                self.queue.discard_results(ident);await self.finish(job,'cancelado',job['runtime']['error']);return
            if history.get('status',{}).get('status_str')!='success':
                await self.finish(job,'fallido','ejecucion_fallida');return
            try:
                self.queue.update(ident,state='importando',stage='importando',progress=80)
                self.backend.import_artifacts(self.store,self.queue,history,job)
            except MotorError as exc:
                self.queue.discard_results(ident);await self.finish(job,'fallido',exc.code);return
            self.queue.update(ident,stage='importado',progress=95)
            return
        if job['state']=='cancelacion_solicitada':
            await self.finish(job,'cancelado',job['runtime']['error']);return
        # No volver a enviar a ciegas tras un reinicio o una respuesta perdida.
        self.queue.update(ident,state='requiere_revision',stage='requiere_revision',error='ejecucion_no_recuperable')
        self.status='requiere_revision'

    async def run(self,once=False):
        if not self.queue.acquire():raise RuntimeError('Ya hay un trabajador con el recurso GPU reservado')
        await self.backend.open();beat=asyncio.create_task(self.heartbeat())
        try:
            while True:
                if beat.done():beat.result()
                try:await self.tick()
                except (aiohttp.ClientError,asyncio.TimeoutError):self.status='motor_desconectado'
                except OSError:self.status='almacenamiento_no_disponible'
                except MotorError:self.status='motor_no_compatible'
                if once:return
                await asyncio.sleep(self.poll)
        finally:
            beat.cancel()
            try:await beat
            except asyncio.CancelledError:pass
            self.queue.release();await self.backend.close()


async def resolve_lost(store,backend,ident):
    queue=Queue(store)
    if not queue.acquire():raise RuntimeError('Deten el trabajador y espera a que expire su reserva antes de resolver')
    await backend.open()
    try:
        job=queue.internal(ident)
        if not job or job['state']!='requiere_revision':raise RuntimeError('El trabajo no esta pendiente de revision')
        native=await backend.queue()
        if native.get('queue_running') or native.get('queue_pending') or await backend.history(job['runtime']['prompt_id']):
            raise RuntimeError('El motor conserva trabajo o historial; reanuda el trabajador para reconciliar')
        queue.discard_results(ident);await backend.clean(job)
        queue.update(ident,state='fallido',stage='fallido',error='perdida_confirmada_por_operador')
    finally:queue.release();await backend.close()
