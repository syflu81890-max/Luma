"""Serial, observable library handover. Never close a database with RPC readers."""
import json,os,threading,time
from pathlib import Path

class WorkspaceHost:
    def __init__(self,profile,factory):
        self.profile=Path(profile);self.profile.mkdir(parents=True,exist_ok=True)
        self.config=self.profile/'library-location.json';self.factory=factory
        location=json.loads(self.config.read_text(encoding='utf-8-sig')) if self.config.exists() else {}
        self.root=Path(location['path']).resolve() if location else (self.profile/'library').resolve()
        offline=bool(location) and not location.get('createIfMissing') and not (self.root/'library.db').exists()
        self.library=None if offline else factory(self.root)
        self.offline=f'资料库离线：{self.root}。请连接存储盘，或在设置中选择已有资料库。' if offline else ''
        self.condition=threading.Condition();self.readers=0;self.switching=False;self.cancel=threading.Event();self.state=dict(status='idle',phase='',path=str(self.root));self.queue=None;self.retired=[]
        if self.library and location.get('createIfMissing'):self._persist(self.root)
        self._start_queue()

    def _persist(self,target):
        temporary=self.config.with_suffix('.pending')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(dict(path=str(target)),stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.config)

    def _start_queue(self):
        if self.library:
            self.queue=threading.Thread(target=self.library.run_queue,daemon=True);self.queue.start()

    def status(self):
        with self.condition:return dict(self.state)

    def phase(self,value):
        with self.condition:self.state['phase']=value
        if self.cancel.is_set():raise ValueError('已取消切换，继续使用原资料库')

    @staticmethod
    def dispose(library,queue=None):
        library.call('shutdown',{})
        # Network avatars may still finish. They check closed before persisting.
        # Reap workers off the handover path and close SQLite only after quiescence.
        def reap():
            if queue:queue.join()
            library.analyzer.thread.join()
            library.avatar_pool.shutdown(wait=True,cancel_futures=True)
            with library.lock:library.db.close()
        thread=threading.Thread(target=reap,daemon=True);thread.start();return thread

    def call(self,method,args=None):
        args=args or {}
        if method=='switchStatus':return self.status()
        if method=='cancelSwitch':
            with self.condition:
                if self.switching:self.cancel.set()
                return self.switching
        if method=='libraryLocation':
            with self.condition:return dict(path=str(self.root),offline=self.offline,switching=self.switching)
        if method=='switchLibrary':return self.switch(args)
        with self.condition:
            if self.switching:raise ValueError('资料库正在切换，请稍候；可查看切换进度或取消')
            library=self.library;self.readers+=1
        try:
            if not library:
                if method=='stats':return dict(total=0,trash=0,revision=0,tags=[],accountCategories=[],albums=[],root=str(self.root),offline=self.offline,pending=0,bytes=0,analysis={})
                if method=='shutdown':return True
                if method=='settings':return {}
                raise ValueError(self.offline)
            return library.call(method,args)
        finally:
            with self.condition:self.readers-=1;self.condition.notify_all()

    def switch(self,args):
        with self.condition:
            if self.switching:raise ValueError('已有资料库切换正在进行，请等待或取消')
            self.switching=True;self.cancel.clear();self.state=dict(status='running',phase='checking',path=str(args.get('path','')),started=time.time())
        old=self.library;new=None;paused=None;committed=False
        try:
            target=Path(args['path']).resolve();mode=args.get('mode','switch')
            if mode not in ('new','switch','migrate'):raise ValueError('无效资料库操作')
            if old and mode=='switch' and target==self.root:return dict(path=str(self.root))
            if mode=='switch' and not (target/'library.db').is_file():raise ValueError('所选位置没有 Luma 资料库')
            if mode=='new' and target.exists() and any(target.iterdir()):raise ValueError('新资料库请选择空文件夹')
            self.phase('waiting')
            with self.condition:
                deadline=time.monotonic()+8
                while self.readers:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise ValueError('上一个操作尚未结束，原资料库保留，请稍后再切换')
                    self.condition.wait(min(.1,remaining))
                    if self.cancel.is_set():raise ValueError('已取消切换，继续使用原资料库')
            if old:
                if not old.lock.acquire(timeout=3):raise ValueError('当前库正在写入文件，请稍后切换；原资料库保留')
                try:
                    if old.completion_hold:raise ValueError('请先取消本轮完成后动作，再切换资料库')
                    if old.active or old.query("SELECT 1 FROM tasks WHERE status IN ('queued','running','waiting')"):raise ValueError('请先暂停采集任务再切换或迁移资料库')
                    if old.busy_operations>len(old.avatar_requested) or old.analyzer.downloading:raise ValueError('请先结束后台写入或浏览器补采、暂停采集，并取消完成后动作')
                    old.maintenance=True;paused=old.analyzer.paused;old.analyzer.paused=True
                finally:old.lock.release()
                self.phase('recovering')
                deadline=time.monotonic()+8
                while getattr(old,'recovery_busy',False):
                    if time.monotonic()>deadline:raise ValueError('正在恢复上次下载的文件，请等待恢复完成再切换')
                    self.phase('recovering');time.sleep(.05)
                self.phase('pausing')
                deadline=time.monotonic()+8
                while old.analyzer.busy:
                    if time.monotonic()>deadline:raise ValueError('本地分析尚未结束，原库保留；请稍后再切换')
                    self.phase('pausing');time.sleep(.05)
            if mode=='migrate':
                if not old:raise ValueError('当前库离线，无法迁移')
                self.phase('copying');old.snapshot(target)
            self.phase('opening');new=self.factory(target)
            self.phase('saving')
            # Hold only this short control lock through the commit: a late cancel
            # either wins before this point or observes a completed handover.
            with self.condition:
                if self.cancel.is_set():raise ValueError('已取消切换，继续使用原资料库')
                self._persist(target);old_queue=self.queue;self.library=new;self.root=target;self.offline='';committed=True
            if old:self.retired.append(self.dispose(old,old_queue))
            self._start_queue()
            return dict(path=str(target))
        finally:
            if not committed:
                if new:self.retired.append(self.dispose(new))
                if old and paused is not None:
                    old.maintenance=False
                    if paused is not None:old.analyzer.paused=paused
                    old.wake.set()
            with self.condition:
                self.switching=False;self.state={**self.state,'status':'idle','phase':'','path':str(self.root)};self.condition.notify_all()
