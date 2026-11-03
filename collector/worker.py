# SPDX-License-Identifier: GPL-2.0-only
"""Isolated downloader. stdout is a JSON event stream, not a console log."""
import contextlib,json,logging,os,re,shutil,sys,threading,time
from pathlib import Path
from common import EXT,media_info,json_text

class ScanState:
    def __init__(self,payload):
        self.limit=int(payload.get('limit') or 0);self.duplicate_streak=0;self.date_old_posts=set();self.mode=payload.get('mode','latest');self.known=set(payload.get('known',[]));self.excluded=set(payload.get('excluded',[]));self.allowed=set(payload.get('selected_keys',[]));self.options=payload.get('options',{});self.watermark=int(payload.get('watermark') or 0);self.top=0;self.old_posts=set();self.seen=set();self.accepted=0;self.capped=False;self.boundary=False
    def decide(self,url,meta):
        post,key,_=media_info(meta,url)
        if not key:key=url
        if key in self.seen:
            self.duplicate_streak+=1
            if self.duplicate_streak>=100:raise RuntimeError('平台连续返回重复媒体，游标无进展；请稍后重试')
            return 'duplicate'
        self.duplicate_streak=0
        self.seen.add(key)
        number=max(int(post) if post.isdigit() else 0,int(meta.get('retweet_id') or 0));self.top=max(self.top,number)
        if self.mode=='latest' and self.watermark and number and number<=self.watermark:
            self.old_posts.add(post)
            if len(self.old_posts)>=10:self.boundary=True;return 'stop'
            return 'old'
        date=str(meta.get('date') or '')[:10]
        if self.options.get('from') and date and date<self.options['from']:
            if not self.options.get('retweets'):
                self.date_old_posts.add(post)
                if len(self.date_old_posts)>=10:self.boundary=True;return 'stop'
            return 'filter'
        if self.options.get('to') and date and date>self.options['to']:return 'filter'
        ext=str(meta.get('extension') or '').lower()
        if '.'+ext not in EXT:return 'filter'
        kind='gif' if ext=='gif' or meta.get('type')=='animated_gif' else 'video' if ext in ('mp4','webm','mov','mkv','m4v') else 'image'
        if kind not in self.options.get('kinds',['image','video','gif']):return 'filter'
        if self.allowed and key not in self.allowed:return 'filter'
        if key in self.excluded:return 'excluded'
        if key in self.known:return 'known'
        if self.limit and self.accepted>=self.limit:self.capped=True;return 'stop'
        self.accepted+=1;return 'preview' if self.mode=='preview' else 'download'

def download():
    payload=json.load(sys.stdin);stream=sys.stdout;event_lock=threading.Lock()
    def emit(kind,**data):
        with event_lock:stream.write(json_text(dict(type=kind,**data))+'\n');stream.flush()
    class EventLog(logging.Handler):
        def emit(self,record):
            text=self.format(record)
            for secret in payload.get('cookies',{}).values():
                if secret:text=text.replace(secret,'[redacted]')
            text=re.sub(r'(auth_token|ct0|authorization|cookie)[\s:=]+\S+',r'\1=[redacted]',text,flags=re.I)
            emit('log',level=record.levelname,message=text[:500])
    logging.basicConfig(level=logging.INFO,handlers=[EventLog()],force=True)
    import gallery_dl.config as config
    from gallery_dl.job import DownloadJob
    from gallery_dl import exception
    config.clear();stage=Path(payload['stage']);stage.mkdir(parents=True,exist_ok=True)
    opts={'base-directory':str(stage),'directory':[],'filename':'{tweet_id}_{num}.{extension}','postprocessors':[{'name':'metadata','mode':'json'}],'retries':3,'timeout':30,'sleep-request':1}
    for key,value in opts.items():config.set(('extractor',),key,value)
    config.set(('extractor','twitter'),'cookies',payload.get('cookies',{}));config.set(('extractor','twitter'),'retweets',bool(payload.get('options',{}).get('retweets')));config.set(('extractor','twitter'),'replies',bool(payload.get('options',{}).get('replies',True)));config.set(('extractor','twitter'),'pinned',False)
    config.set(('extractor','twitter'),'videos',True);config.set(('extractor','twitter'),'include',['media'])
    config.set(('downloader','hls'),'ffmpeg',payload.get('ffmpeg') or 'ffmpeg')
    if payload.get('proxy'):config.set(('extractor',),'proxy',payload['proxy'])
    state=ScanState(payload)
    def check_disk():
        if shutil.disk_usage(stage).free<max(16,int(payload.get('minFreeMiB',512)))*1048576:raise OSError('磁盘空间不足，采集已停止')
    from gallery_dl.output import NullOutput
    class ProgressOutput(NullOutput):
        last=0
        def progress(self,bytes_total,bytes_downloaded,bytes_per_second):
            if time.monotonic()-self.last>=1:
                self.last=time.monotonic();check_disk();emit('progress',speed=bytes_per_second,downloaded=bytes_downloaded,total=bytes_total)
    class Job(DownloadJob):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.out=ProgressOutput()
            extr=self.extractor
            if hasattr(extr,'_assign_user'):
                original=extr._assign_user
                def assign(user):
                    from account_health import user_state
                    state=user_state(user)
                    if state['state']=='active':
                        original(user);emit('account_state',**state,profile=extr._user);return
                    emit('account_state',**state);return original(user)
                extr._assign_user=assign
        def handle_url(self,url,meta):
            decision=state.decide(url,meta);post,key,_=media_info(meta,url)
            emit('item',key=key,url=url,metadata=meta,decision=decision,top=state.top)
            if decision=='stop':raise exception.StopExtraction()
            if decision!='download':return
            check_disk();super().handle_url(url,meta)
            destination=Path(self.pathfmt.realpath)
            if destination.is_file():emit('file',path=str(destination),metadata=meta,url=url,key=key)
    code=0;emit('ready')
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if payload.get('selected'):
                import requests
                for candidate in payload['selected']:
                    meta=candidate['metadata'];url=candidate['url'];decision=state.decide(url,meta)
                    emit('item',key=media_info(meta,url)[1],url=url,metadata=meta,decision=decision,top=state.top)
                    if decision=='stop':break
                    if decision!='download':continue
                    key=media_info(meta,url)[1];destination=stage/(key.replace(':','_')+'.'+meta.get('extension','jpg'));temporary=Path(str(destination)+'.part')
                    session=requests.Session()
                    if payload.get('proxy'):session.proxies.update(http=payload['proxy'],https=payload['proxy'])
                    check_disk()
                    with session.get(url,timeout=(15,45),stream=True) as response:
                        response.raise_for_status()
                        with temporary.open('wb') as f:
                            received=0;start=time.monotonic();last=0
                            for chunk in response.iter_content(512*1024):
                                if chunk:f.write(chunk);received+=len(chunk)
                                if time.monotonic()-last>1:last=time.monotonic();check_disk();emit('progress',speed=received/max(.01,last-start),downloaded=received)
                            f.flush();os.fsync(f.fileno())
                    Path(str(destination)+'.json').write_text(json_text(meta),encoding='utf-8');os.replace(temporary,destination);emit('file',path=str(destination),metadata=meta,url=url,key=key)
            else:code=Job(payload['url']).run() or 0
    except Exception as exc:
        logging.exception('%s: %s',type(exc).__name__,str(exc));code=1
    emit('finished',code=code,top=str(state.top),capped=state.capped,boundary=state.boundary,accepted=state.accepted)
    return code
