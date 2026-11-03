from collector_client import collector_command
import base64,hashlib,io,json,os,queue,re,shutil,subprocess,sys,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from PIL import Image
from store import Store,EXT,now,json_text,normalize,handle_from_url,media_info
from analysis import Analyzer
from management import Management
from assistant import Assistant
from similarity_cache import PersistentSimilarity as Similarity
from catalog import Catalog

def next_run(rule,reference=None):
    reference=reference or datetime.now(timezone.utc)
    if not rule.get('enabled'):return ''
    if rule.get('type')=='daily':
        hour,minute=map(int,rule.get('time','09:00').split(':'));offset=int(rule.get('offset',480));local=reference.astimezone(timezone(timedelta(minutes=offset)));target=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if target<=local:target+=timedelta(days=1)
        return target.astimezone(timezone.utc).isoformat()
    return (reference+timedelta(hours=max(.5,float(rule.get('hours',6))))).isoformat()

class Library(Catalog,Similarity,Assistant,Management,Store):
    def __init__(self,root,defer_recovery=False):
        super().__init__(root);self.closed=False;self.active=None;self.process=None;self.session_cookies={};self.session_ready=False;self.wake=threading.Event();self.maintenance=False;self.avatar_requested=set()
        self.avatar_pool=ThreadPoolExecutor(max_workers=2);self.completion_ids=set();self.completion_hold=False;self.completion_frozen=False;self.completion_interrupted='';self.completion_wait_analysis=False;self.completion_generation=0;self.busy_operations=0
        self.recovery_pending=defer_recovery;self.recovery_busy=False;self.recovery_error=''
        if not defer_recovery:self.recover_initial()
        self.analyzer=Analyzer(self)
    def recover_initial(self):
        for t in self.query('SELECT * FROM tasks'):
            if self.closed or self.maintenance:return False
            if (self.root/'staging'/t['id']).exists():self.drain_stage(t)
        self.recover_task_counts();self.recovery_pending=False;return True
    def add_task(self,a,origin='manual'):
        if shutil.disk_usage(self.root).free<max(16,int(self.settings().get('minFreeMiB',512)))*1048576:raise ValueError('资料库所在磁盘空间不足，未开始新任务；可在设置中调整预留空间')
        url=normalize(a['url']);mode=a.get('mode','latest')
        if mode not in ['latest','history','preview','selected']:raise ValueError('无效采集方式')
        if mode=='selected' and any(c.get('task')==getattr(self,'browser_capture',None) for c in a.get('selected',[])):raise ValueError('浏览器仍在补采，请关闭补采窗口并等待列表保存后，再下载所选媒体')
        limit=int(a.get('limit') or 0)
        if not 0<=limit<=1000000:raise ValueError('数量为 0（不限）或 1–1000000')
        opts=dict(a.get('options') or {})
        for key in ['from','to']:
            if opts.get(key):datetime.strptime(opts[key],'%Y-%m-%d')
        if opts.get('from') and opts.get('to') and opts['from']>opts['to']:raise ValueError('开始日期不能晚于结束日期')
        handle=handle_from_url(url);aid=self.ensure_account(handle)
        if aid and self.query("SELECT 1 FROM accounts WHERE id=? AND availability='suspended'",(aid,)):raise ValueError('该账号在封禁池中，请检测到恢复正常后再采集')
        if aid and not re.search(r'/status/\d+',url):url='https://x.com/'+handle+'/media'
        if a.get('cookies') is not None:self.session_cookies=a['cookies'];self.session_ready=bool(self.session_cookies.get('auth_token'))
        if mode=='selected':opts['selected']=a.get('selected',[])
        ident=uuid.uuid4().hex
        with self.transaction() as db:
            running=db.execute("SELECT id FROM tasks WHERE account=? AND account<>'' AND status IN ('queued','running','waiting') LIMIT 1",(aid,)).fetchone()
            if running:return dict(id=running['id'],merged=True)
            db.execute('INSERT INTO tasks(id,url,limit_count,status,created,updated,account,mode,options,origin) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,url,limit,'queued',now(),now(),aid,mode,json_text(opts),origin))
            if aid and origin=='manual':db.execute('UPDATE accounts SET auto_paused=0 WHERE id=?',(aid,))
            if self.completion_hold and origin=='manual':self.completion_ids.add(ident);self.completion_generation+=1
        self.wake.set();return dict(id=ident,merged=False)
    def task_action(self,a):
        rows=self.query('SELECT * FROM tasks WHERE id=?',(a['id'],))
        if not rows:raise ValueError('任务不存在')
        t=rows[0];action=a['action']
        if action=='resume' and self.query("SELECT 1 FROM accounts WHERE id=? AND availability='suspended'",(t['account'],)):raise ValueError('该账号仍在封禁池中，暂不能恢复采集')
        if a.get('cookies') is not None:self.session_cookies=a['cookies'];self.session_ready=bool(self.session_cookies.get('auth_token'))
        if action=='resume' and t['mode']=='legacy':return self.add_task(dict(url=t['url'],limit=t['limit_count']))
        if action not in ['pause','resume','cancel']:raise ValueError('无效任务操作')
        with self.lock:
            if self.completion_hold:
                self.completion_generation+=1
                if action in ('pause','cancel'):self.completion_interrupted='你暂停或取消了任务，完成后动作已停止，请处理后重新启用'
                elif action=='resume':self.completion_ids.add(t['id'])
            if action=='resume':self.write('UPDATE tasks SET attempt=0,hidden=0,updated=? WHERE id=?',(now(),t['id']))
            if action=='resume' and t['account'] and self.query("SELECT 1 FROM tasks WHERE account=? AND id<>? AND status IN ('running','queued','waiting')",(t['account'],t['id'])):raise ValueError('该账号已有采集任务，请等待或暂停后再试')
            self.write('UPDATE tasks SET status=?,retry_at=?,message=? WHERE id=?',({'pause':'paused','resume':'queued','cancel':'cancelled'}[action],'',{'pause':'已手动暂停，下载好的内容已保留','resume':'等待继续采集','cancel':'已取消；已入库内容保留'}[action],t['id']))
            if t['account']:self.write('UPDATE accounts SET auto_paused=? WHERE id=?',(0 if action=='resume' else 1,t['account']))
            if self.active==t['id'] and self.process and self.process.poll() is None:self.process.terminate()
        self.wake.set();return True
    def drain_stage(self,t):
        stage=self.root/'staging'/t['id'];totals=dict(added=0,duplicates=0,excluded=0,failed=0)
        for p in list(stage.rglob('*')):
            if self.closed or self.maintenance:break
            if p.suffix.lower() not in EXT or not p.is_file():continue
            side=Path(str(p)+'.json');meta={}
            if side.exists():
                try:meta=json.loads(side.read_text(encoding='utf-8'))
                except (ValueError,OSError):continue
            post,_,author=media_info(meta,t['url']);source=f"https://x.com/{author.get('name','i')}/status/{post}" if post else t['url']
            result=self.ingest([p],source,meta,t['id'] if t['mode']!='legacy' else '',t['account'])
            for key in totals:totals[key]+=result[key]
            if not result['failed']:p.unlink(missing_ok=True);side.unlink(missing_ok=True)
        return totals
    def run_task(self,t):
        ident=t['id'];started_at=time.monotonic();previous_elapsed=t.get('elapsed',0) or 0;downloaded=t.get('downloaded_bytes',0) or 0;stage=self.root/'staging'/ident;stage.mkdir(exist_ok=True);events=queue.Queue();errors=[];last_activity=time.monotonic();finished={};scanned=0
        decisions={};verified=False;result=None
        options=json.loads(t['options'] or '{}');account=self.query('SELECT * FROM accounts WHERE id=?',(t['account'],))
        known=[r['media_key'] for r in self.query("SELECT m.media_key FROM media m JOIN photos p ON p.id=m.photo WHERE p.trash<>2 UNION SELECT media_key FROM excluded_media")];selected=[]
        for candidate in options.get('selected',[]):
            rows=self.query('SELECT * FROM candidates WHERE task=? AND media_key=?',(candidate['task'],candidate['key']))
            if rows:selected.append(dict(url=rows[0]['url'],metadata=json.loads(rows[0]['metadata'])))
        from media_utils import ffmpeg_path
        payload=dict(ffmpeg=ffmpeg_path(),url=t['url'],limit=t['limit_count'],stage=str(stage),cookies=self.session_cookies,options=options,mode=t['mode'],known=known,excluded=[r['media_key'] for r in self.query('SELECT media_key FROM excluded_media')],watermark=account[0]['watermark'] if account else '0',selected=selected,proxy=self.settings().get('proxy',''),minFreeMiB=max(16,int(self.settings().get('minFreeMiB',512))))
        with self.lock:
            current=self.query('SELECT status FROM tasks WHERE id=?',(ident,))
            if not current or current[0]['status']!='queued':return
            self.active=ident;self.write("UPDATE tasks SET status='running',speed=0,started=?,message='正在连接 X，检查更新…',updated=? WHERE id=?",(now(),now(),ident))
            if t['account']:self.write('UPDATE accounts SET last_checked=? WHERE id=?',(now(),t['account']))
        process=None
        try:
            command=collector_command('--download')
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.process=process
            def read():
                for line in iter(process.stdout.readline,b''):
                    try:events.put(json.loads(line.decode('utf-8')))
                    except (ValueError,UnicodeError):pass
            reader=threading.Thread(target=read,daemon=True);reader.start();process.stdin.write(json_text(payload).encode('utf-8'));process.stdin.close()
            self.drain_stage(t);last_message=0;timed_out=False
            while process.poll() is None or reader.is_alive() or not events.empty():
                try:event=events.get(timeout=.5)
                except queue.Empty:event=None
                if event:
                    last_activity=time.monotonic();kind=event.get('type')
                    if kind=='item':
                        scanned+=1;meta=event['metadata'];post,key,author=media_info(meta,t['url']);self.ensure_account(author.get('name',''),author);decision=event['decision']
                        decisions[decision]=decisions.get(decision,0)+1
                        if t['account'] and meta.get('date'):self.write('UPDATE accounts SET last_published=MAX(last_published,?) WHERE id=?',(str(meta['date']).replace(' ','T'),t['account']))
                        if decision=='preview':self.write('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?)',(ident,key,event['url'],json_text(meta)))
                        if decision in ('known','excluded'):
                            rows=self.query('SELECT photo FROM media WHERE media_key=?',(key,));excluded=bool(self.query('SELECT 1 FROM excluded_media WHERE media_key=?',(key,)))
                            if rows:
                                photo=rows[0]['photo'];self._source(photo,f"https://x.com/{author.get('name','i')}/status/{post}",meta,t['account'])
                                with self.transaction() as db:self.record_item(ident,key,photo,'excluded' if excluded else 'duplicate',db)
                            elif excluded:
                                rows=self.query('SELECT photo FROM excluded_media WHERE media_key=?',(key,))
                                with self.transaction() as db:self.record_item(ident,key,rows[0]['photo'] if rows else '','excluded',db)
                        if event.get('top') and t['account']:self.write('UPDATE accounts SET pending_top=CAST(MAX(CAST(pending_top AS INTEGER),?) AS TEXT) WHERE id=?',(int(event['top']),t['account']))
                    elif kind=='account_state':
                        verified=verified or event.get('state')=='active'
                        if t['account']:self.set_account_health(t['account'],event)
                    elif kind=='file':
                        path=Path(event.get('path',''));downloaded+=path.stat().st_size if path.is_file() else 0;self.drain_stage(t)
                    elif kind=='progress':self.write('UPDATE tasks SET speed=? WHERE id=?',(max(0,float(event.get('speed',0))),ident))
                    elif kind=='log':
                        if event.get('level') in ['ERROR','WARNING','CRITICAL']:errors.append(event['message']);errors=errors[-4:]
                        message=event.get('message','')
                        if any(word in message.lower() for word in ['429','rate limit','sleep','retry']):self.write('UPDATE tasks SET message=? WHERE id=?',('等待平台响应或重试：'+message[:160],ident))
                    elif kind=='finished':finished=event
                if time.monotonic()-last_message>1:self.write('UPDATE tasks SET scanned=?,elapsed=?,downloaded_bytes=?,result_json=?,updated=? WHERE id=?',(scanned,previous_elapsed+time.monotonic()-started_at,downloaded,json_text(dict(counts=decisions,verified=verified,complete=False)),now(),ident));last_message=time.monotonic()
                if self.closed:
                    if process.poll() is None:process.terminate()
                    break
                if time.monotonic()-last_activity>900:timed_out=True;process.terminate();break
            code=process.wait(timeout=15);reader.join(timeout=2);import_result=self.drain_stage(t);self.write('UPDATE tasks SET failed=? WHERE id=?',(import_result['failed'],ident));row=self.query('SELECT * FROM tasks WHERE id=?',(ident,))[0]
            if row['status']!='running':return
            reason=''
            if timed_out:status='failed';message='采集引擎连续 15 分钟没有活动，已停止。已有内容保留，可重试。'
            elif not finished and not code:status='failed';message='引擎未返回完成标记。进度边界未推进，可重试；已有媒体保留。'
            elif import_result['failed']:status='failed';message=f"{import_result['failed']} 个文件已下载但无法导入，临时文件保留，可检查格式后重试。"
            elif code or finished.get('code'):
                text=' / '.join(errors[-2:]) or f'引擎退出码 {code}'
                from collection_results import classify_failure
                status,reason,message=classify_failure(text);message+=' '+text[:300]
                if status=='waiting':
                    if t['attempt']<2:self.write('UPDATE tasks SET retry_at=?,attempt=attempt+1 WHERE id=?',((datetime.now(timezone.utc)+timedelta(minutes=(15 if reason=='rate_limited' else 2)*(t['attempt']+1))).isoformat(),ident))
                    else:status='failed';message='重试后仍未完成：'+message
            elif finished.get('capped'):status='partial';message='已达到本次数量上限，仍可能有内容待补齐。继续采集可补齐，进度边界尚未推进。'
            elif t['mode']=='preview':status='completed';message=f'预览完成：找到 {self.query("SELECT COUNT(*) n FROM candidates WHERE task=?",(ident,))[0]["n"]} 项，可勾选下载。'
            else:
                status='completed';message=f"已入库 {row['imported']} 项 · 重复 {row['duplicates']} 项 · 已删跳过 {row['excluded']} 项"
                if not row['imported']:
                    from collection_results import describe_zero
                    message=describe_zero(decisions,verified,bool(finished.get('boundary')))
                    if not scanned and not verified:status='partial';reason='empty_unverified'
                    if not scanned and account and int(account[0]['pending_top'] or 0)>int(account[0]['watermark'] or 0):status='partial';reason='empty_pending';message='上轮仍有未补齐范围，本轮空响应无法确认完整；保留原进度，请继续补齐或使用浏览器补采。'
                if status=='completed' and t['mode']=='latest' and t['account'] and not options.get('from') and not options.get('to') and set(options.get('kinds',['image','video','gif']))=={'image','video','gif'}:self.write("UPDATE accounts SET watermark=CAST(MAX(CAST(watermark AS INTEGER),CAST(pending_top AS INTEGER),?) AS TEXT),pending_top='0' WHERE id=?",(int(finished.get('top','0')),t['account']))
            result=dict(counts=decisions,verified=verified,complete=status=='completed',boundary=bool(finished.get('boundary')),capped=bool(finished.get('capped')))
            self.write('UPDATE tasks SET status=?,message=?,capped=?,result_json=?,reason_code=?,scanned=?,updated=? WHERE id=?',(status,message,int(bool(finished.get('capped'))),json_text(result),reason,scanned,now(),ident))
            if status=='needs_login' and t['account']:self.write('UPDATE accounts SET auto_paused=1 WHERE id=?',(t['account'],))
            if t['account']:self.write('UPDATE accounts SET last_checked=? WHERE id=?',(now(),t['account']))
            if t['account'] and status=='completed' and t['mode'] in ('latest','history') and not options.get('from') and not options.get('to') and set(options.get('kinds',['image','video','gif']))=={'image','video','gif'}:self.write('UPDATE accounts SET last_success=? WHERE id=?',(now(),t['account']))
        except Exception as exc:self.write("UPDATE tasks SET status='failed',message=?,updated=? WHERE id=?",(f'后台处理失败：{type(exc).__name__}: {str(exc)[:180]}。已下载内容保留。',now(),ident))
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            if process:
                if process.stdout:process.stdout.close()
                if process.stdin and not process.stdin.closed:process.stdin.close()
            with self.lock:
                self.write('UPDATE tasks SET elapsed=?,downloaded_bytes=?,speed=0,scanned=?,result_json=? WHERE id=?',(previous_elapsed+time.monotonic()-started_at,downloaded,scanned,json_text(result or dict(counts=decisions,verified=verified,complete=False)),ident));self.active=None;self.process=None
    def run_queue(self):
        while not self.closed:
            if self.recovery_pending and not self.maintenance:
                with self.lock:
                    if self.maintenance or self.closed:continue
                    self.recovery_busy=True
                try:
                    if not self.recover_initial():continue
                except Exception as exc:
                    self.recovery_error=str(exc);self.wake.wait(1);self.wake.clear();continue
                finally:self.recovery_busy=False
            if not self.maintenance:self.reconcile_layout(limit=20);self.region_backfill()
            if self.maintenance or not self.session_ready:self.wake.wait(.5);self.wake.clear();continue
            if self.query("SELECT 1 FROM tasks WHERE status='waiting' AND retry_at<=?",(now(),)):self.write("UPDATE tasks SET status='queued',message='正在重新排队' WHERE status='waiting' AND retry_at<>'' AND retry_at<=?",(now(),))
            rows=self.query("SELECT t.* FROM tasks t LEFT JOIN accounts ac ON ac.id=t.account WHERE t.status='queued' AND COALESCE(ac.availability,'unknown')<>'suspended' ORDER BY t.created LIMIT 1")
            if rows:self.run_task(rows[0])
            else:self.wake.wait(.7);self.wake.clear()
    def schedule_tick(self,a):
        with self.lock:
            self.session_cookies=a.get('cookies',self.session_cookies);self.session_ready=bool(self.session_cookies.get('auth_token'));self.wake.set();current=now();created=[]
            if self.completion_hold or self.maintenance or self.closed or self.settings().get('schedulerEnabled') is False:return []
            for account in self.query("SELECT * FROM accounts WHERE auto_paused=0 AND availability<>'suspended'"):
                rule=json.loads(account['schedule'] or '{}')
                if not rule.get('enabled'):continue
                due=(not account['next_run'] and rule.get('onOpen',True)) or (account['next_run'] and account['next_run']<=current)
                if not due:continue
                task=self.add_task(dict(url='@'+account['handle'],limit=int(rule.get('limit') or 0),options=rule.get('options',{})),origin='schedule');created.append(task);self.write('UPDATE accounts SET next_run=? WHERE id=?',(next_run(rule),account['id']))
            return created
    def schedule(self,a):
        rule=dict(a['rule']);rule['limit']=int(rule.get('limit') or 0)
        if not 0<=rule['limit']<=1000000:raise ValueError('数量上限无效')
        next_run(rule) # Validate the complete rule before persisting it.
        next_value=now() if rule.get('onOpen') and rule.get('enabled') else next_run(rule);self.write('UPDATE accounts SET schedule=?,next_run=?,auto_paused=0 WHERE id=?',(json_text(rule),next_value,a['id']));return True
    def import_files(self,paths):
        ident=uuid.uuid4().hex;self.write('INSERT INTO tasks(id,url,limit_count,status,created,updated,mode) VALUES(?,?,?,?,?,?,?)',(ident,'本地导入',len(paths),'running',now(),now(),'import'));result=self.ingest(paths,task=ident);self.write('UPDATE tasks SET status=?,message=?,updated=? WHERE id=?',('completed',f"导入 {result['added']} 项 · 重复 {result['duplicates']} 项 · 排除 {result['excluded']} 项 · 失败 {result['failed']} 项",now(),ident));return dict(result,batch=ident)
    def fetch_avatar(self,aid):
        with self.lock:
            if self.closed or self.maintenance:return
            rows=self.query('SELECT avatar_url FROM accounts WHERE id=?',(aid,))
        if not rows:return
        url=rows[0]['avatar_url'];host=urlparse(url).hostname or ''
        if urlparse(url).scheme!='https' or not host.endswith('.twimg.com'):return
        import requests
        response=requests.get(url,timeout=(10,20));response.raise_for_status();im=Image.open(io.BytesIO(response.content)).convert('RGB');im.thumbnail((400,400));out=io.BytesIO();im.save(out,format='JPEG',quality=90);data=out.getvalue();rel='avatars/history/'+hashlib.sha256(data).hexdigest()+'.jpg';(self.root/rel).parent.mkdir(parents=True,exist_ok=True)
        with self.lock:
            if self.closed or self.maintenance:return
            if not (self.root/rel).exists():(self.root/rel).write_bytes(data)
            current=self.query('SELECT pinned_avatar FROM accounts WHERE id=?',(aid,))
            update=dict(id=aid,avatar_path=rel,avatar_fetched_url=url)
            if current and not current[0]['pinned_avatar']:update['pinned_avatar']=rel
            self.save_account(update)
    def request_avatar(self,ident,url=''):
        if ident in self.avatar_requested or self.closed or self.maintenance:return
        if getattr(self,'avatar_cooldowns',{}).get((ident,url),0)>time.monotonic():return
        with self.lock:
            if self.completion_frozen or self.closed or self.maintenance:return
            self.avatar_requested.add(ident);self.busy_operations+=1;self.completion_generation+=1
        def fetch():
            try:self.fetch_avatar(ident)
            except Exception:
                if not hasattr(self,'avatar_cooldowns'):self.avatar_cooldowns={}
                self.avatar_cooldowns[(ident,url)]=time.monotonic()+120
            finally:
                with self.lock:self.avatar_requested.discard(ident);self.busy_operations-=1
        self.avatar_pool.submit(fetch)
    def call(self,method,a):
        reads={'accountChoices','notePresets','accountRemovePlan','mediaAccounts','stats','list','selectIds','detail','image','files','copyFiles','accounts','accountIds','account','avatar','tasks','taskPage','taskIds','candidates','candidatePage','candidateIds','candidateImage','storageStatus','storageFolder','settings','similar','check','aiSearch','completion','assistantDuplicates','assistantFolder','assistantJob','assistantJobs','assistantPlanInfo','dashboard','collections','accountHistory','historyAvatar','accountHealthStatus','similarStatus','similarPage','savedViews','followingStatus','followingPage','backgroundStatus'}
        mutation=method not in reads and method not in {'shutdown','scheduleTick'}
        with self.lock:
            if mutation and (self.completion_frozen or self.maintenance):raise ValueError('正在保存或维护资料库，请先取消完成后动作或等待维护结束')
            if mutation:self.busy_operations+=1;self.completion_generation+=1
        try:return self._call(method,a)
        finally:
            if mutation:
                with self.lock:self.busy_operations-=1
    def _call(self,method,a):
        if method=='notePresets':return self.note_presets()
        if method=='notePresetUse':self.remember_note(a['text']);return self.note_presets()
        if method=='accountRemovePlan':return self.account_remove_plan(a)
        if method=='accountRemove':return self.remove_account(a)
        if method=='accountRegion':return self.infer_account_region(a['id'])
        if method=='mediaAccounts':return self.query('SELECT ac.* FROM accounts ac JOIN account_photos ap ON ac.id=ap.account WHERE ap.photo=?',(a['id'],))
        if method=='accountChoices':return self.query('SELECT id,handle,alias,name FROM accounts ORDER BY COALESCE(NULLIF(alias,\'\'),name),handle LIMIT 5000')
        if method=='similarIgnore':return self.ignore_similar(a)
        if method=='savedViews':return self.saved_views()
        if method=='saveView':return self.save_view(a)
        if method=='deleteView':self.write('DELETE FROM saved_views WHERE id=?',(a['id'],));return self.saved_views()
        if method=='backgroundStatus':return self.background_status()
        if method=='followingStatus':return self.following_status(a)
        if method=='followingPage':return self.following_page(a)
        if method=='followingStart':return self.start_following(a)
        if method=='followingImport':return self.import_following(a)
        if method=='followingCancel':
            self.following_cancelled=True;child=getattr(self,'following_process',None)
            if child and child.poll() is None:child.terminate()
            return self.following_status()
        if method=='browserTask':
            rows=self.query('SELECT * FROM tasks WHERE id=?',(a['id'],))
            if not rows:raise ValueError('任务不存在')
            row=rows[0]
            if row['mode']=='import' or row['status'] in ('queued','running','waiting'):raise ValueError('请先暂停该任务再使用浏览器补采')
            return dict(id=row['id'],url=row['url'],account=row['account'],options=json.loads(row['options']),limit=row['limit_count'])
        if method=='browserPrepare':
            if getattr(self,'browser_capture',None):raise ValueError('另一个浏览器补采尚未结束')
            row=self._call('browserTask',a);options={**row['options'],'browserSource':row['id'],'retweets':False,'replies':True,'browserPage':row['url']}
            if self.query("SELECT 1 FROM tasks WHERE account=? AND status IN ('queued','running','waiting')",(row['account'],)):raise ValueError('此账号还有活动任务，请先暂停后再补采')
            ident=uuid.uuid4().hex
            self.write("INSERT INTO tasks(id,url,account,mode,limit_count,status,created,updated,options,origin,message) VALUES(?,?,?,'preview',?,'paused',?,?,?,'browser','正在读取已登录浏览器中的可见媒体')",(ident,row['url'],row['account'],row['limit'],now(),now(),json_text(options)))
            self.browser_capture=ident;self.busy_operations+=1
            if self.completion_hold:self.completion_ids.add(ident)
            return dict(id=ident)
        if method=='browserCandidates':
            rows=self.query("SELECT * FROM tasks WHERE id=? AND status='paused'",(a['id'],))
            if not rows or 'browserSource' not in json.loads(rows[0]['options']):raise ValueError('浏览器补采任务不存在或已结束')
            count=0
            from browser_media import extract_candidates
            for item in extract_candidates(a.get('data') or {},a.get('owner',''),a.get('ownerId',''),a.get('post','')):
                self.write('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)',(a['id'],item['key'],item['url'],json_text(item['metadata'])));count+=1
            self.write('UPDATE tasks SET scanned=(SELECT COUNT(*) FROM candidates WHERE task=?),updated=?,message=? WHERE id=?',(a['id'],now(),'浏览器页面发现媒体；关闭页面后可勾选下载',a['id']))
            return dict(discovered=count,total=self.query('SELECT COUNT(*) n FROM candidates WHERE task=?',(a['id'],))[0]['n'])
        if method=='browserFinish':
            return self.finish_browser(a)
        if method.startswith('assistant'):return self.assistant_call(method,a)
        if method=='similarStatus':return self.similar_status()
        if method=='similarScan':return self.start_similar_scan(a)
        if method=='similarPage':return self.similar_page(a)
        if method=='similarPlan':return self.similar_plan(a)
        if method=='similarCancel':
            if getattr(self,'similar_job',None):self.similar_job['cancelled']=True
            return self.similar_status()
        if method=='dashboard':return self.dashboard()
        if method=='collections':return self.collections()
        if method=='collectionAction':
            if a['action'] in ('add','remove'):self.remember_accounts(a.get('ids',[]))
            return self.collection_action(a)
        if method=='accountHistory':return self.account_history(a)
        if method=='historyAvatar':
            rows=self.query('SELECT avatar_path,custom_avatar FROM account_history WHERE id=?',(a['id'],))
            if not rows:return ''
            path=rows[0]['custom_avatar'] or rows[0]['avatar_path'];file=self.path(path) if path else None
            return 'data:image/jpeg;base64,'+base64.b64encode(file.read_bytes()).decode() if file and file.is_file() else ''
        if method=='accountHealthStatus':return self.health_status()
        if method=='accountHealthCheck':return self.start_health_check(a)
        if method=='collectAll':return self.collect_all(a)
        if method=='stats':return dict(self.stats(),savedViews=self.saved_views(),analysis=self.analyzer.status(),active=self.active,queueWaitingLogin=not self.session_ready,queued=self.query("SELECT COUNT(*) n FROM tasks WHERE status='queued'")[0]['n'],storage=self.storage_status(),freeBytes=shutil.disk_usage(self.root).free)
        if method=='list':return self.list_photos(a)
        if method=='selectIds':return self.select_ids(a)
        if method=='detail':return self.detail(a['id'])
        if method=='image':return self.image(a['id'],a.get('full',False))
        if method=='files':return self.file_paths(a['ids'])
        if method=='copyFiles':
            from win_clipboard import copy_files
            return copy_files(self.file_paths(a['ids']))
        if method=='update':return self.edit(a)
        if method=='undo':return self.undo()
        if method=='purge':return self.purge(a['ids'])
        if method=='accounts':return self.account_rows(a)
        if method=='accountIds':return self.account_rows(a,True)
        if method=='accountBatch':
            if a['action'] in ('rating','categories'):self.remember_accounts(a.get('ids',[]))
            return self.account_batch(a)
        if method=='taskPage':return self.task_page(a)
        if method=='taskIds':return self.task_page(a,True)
        if method=='taskBatch':return self.task_batch(a)
        if method=='completion':return self.completion(a)
        if method=='account':return self.account_detail(a['id'])
        if method=='saveAccount':self.remember_accounts([a['id']]);return self.save_account(a)
        if method=='addAccount':return self.ensure_account(handle_from_url(normalize(a['value'])))
        if method=='schedule':return self.schedule(a)
        if method=='scheduleTick':return self.schedule_tick(a)
        if method=='avatar':
            rows=self.query('SELECT custom_avatar,avatar_path,avatar_url,avatar_fetched_url,pinned_avatar FROM accounts WHERE id=?',(a['id'],))
            if not rows:return ''
            if rows[0]['avatar_url'] and (not rows[0]['avatar_path'] or rows[0]['avatar_url']!=rows[0]['avatar_fetched_url']):self.request_avatar(a['id'],rows[0]['avatar_url'])
            rel=rows[0]['custom_avatar'] or rows[0]['pinned_avatar'] or rows[0]['avatar_path'];return 'data:image/jpeg;base64,'+base64.b64encode(self.path(rel).read_bytes()).decode() if rel and self.path(rel).is_file() else ''
        if method=='customAvatar':
            im=Image.open(a['path']).convert('RGB');im.thumbnail((400,400));rel='avatars/custom-'+uuid.uuid4().hex+'.jpg';im.save(self.root/rel,quality=90);return self.save_account(dict(id=a['id'],custom_avatar=rel))
        if method=='refreshAvatar':
            self.fetch_avatar(a['id'])
            self.write('UPDATE accounts SET pinned_avatar=avatar_path WHERE id=?',(a['id'],));return True
        if method=='resetAccount':
            self.write("UPDATE accounts SET watermark='0',pending_top='0' WHERE id=?",(a['id'],))
            if a.get('clearExcluded'):
                with self.transaction() as db:db.execute('DELETE FROM excluded_media WHERE photo IN (SELECT photo FROM account_photos WHERE account=?)',(a['id'],));db.execute('DELETE FROM excluded_content WHERE photo IN (SELECT photo FROM account_photos WHERE account=?)',(a['id'],))
            return True
        if method=='tasks':return self.query('SELECT * FROM tasks ORDER BY created DESC LIMIT 200')
        if method=='addTask':return self.add_task(a)
        if method=='taskAction':return self.task_action(a)
        if method=='candidateIds':return [r['media_key'] for r in self.query('SELECT media_key FROM candidates WHERE task=? ORDER BY media_key',(a['id'],))]
        if method=='candidatePage':
            size=100;total=self.query('SELECT COUNT(*) n FROM candidates WHERE task=?',(a['id'],))[0]['n'];page=max(1,int(a.get('page',1)))
            return dict(items=self.query("SELECT * FROM candidates WHERE task=? ORDER BY CAST(json_extract(metadata,'$.tweet_id') AS INTEGER) DESC,CAST(json_extract(metadata,'$.num') AS INTEGER),media_key LIMIT ? OFFSET ?",(a['id'],size,(page-1)*size)),total=total,pages=max(1,(total+size-1)//size),page=page)
        if method=='candidates':return self.query('SELECT * FROM candidates WHERE task=? LIMIT 200',(a['id'],))
        if method=='candidateImage':
            rows=self.query('SELECT url FROM candidates WHERE task=? AND media_key=?',(a['task'],a['key']))
            if not rows or urlparse(rows[0]['url']).hostname!='pbs.twimg.com':return ''
            cache=self.root/'thumbs'/('candidate-'+hashlib.sha256(rows[0]['url'].encode()).hexdigest()+'.jpg')
            if cache.is_file():return 'data:image/jpeg;base64,'+base64.b64encode(cache.read_bytes()).decode()
            import requests
            url=re.sub(r'name=[^&]+','name=small',rows[0]['url']);response=requests.get(url,timeout=20);response.raise_for_status();im=Image.open(io.BytesIO(response.content)).convert('RGB');im.thumbnail((320,320));out=io.BytesIO();im.save(out,format='JPEG',quality=80);cache.write_bytes(out.getvalue());return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
        if method=='import':return self.import_files(a['paths'])
        if method=='importEdit':
            result=self.import_files(a['paths'])
            for path in a['paths']:
                with open(path,'rb') as stream:ident=hashlib.file_digest(stream,'sha256').hexdigest()
                if ident!=a['parent']:self.write('UPDATE photos SET parent=? WHERE id=?',(a['parent'],ident))
            return result
        if method=='importFolder':return self.import_files([str(p) for p in Path(a['path']).rglob('*') if p.is_file() and p.suffix.lower() in EXT])
        if method=='export':return self.export(a)
        if method=='album':return self.album(a)
        if method=='settings':return self.settings()
        if method=='saveSettings':return self.save_settings(a)
        if method=='similar':return self.similar()
        if method=='check':return dict(self.check(),storage=self.storage_status())
        if method=='storageFolder':
            from storage_layout import folder_name
            rows=self.query('SELECT handle FROM accounts WHERE id=?',(a.get('id',''),))
            path=self.root/'originals'/(folder_name('@'+rows[0]['handle']) if rows else '')
            if not path.is_dir():raise ValueError('此账号还没有已保存的媒体目录')
            return str(path)
        if method=='storageStatus':return self.storage_status()
        if method=='organizeStorage':return self.reconcile_layout(limit=None,retry=True)
        if method=='clearCache':
            with self.lock:
                count=0
                for path in (self.root/'thumbs').glob('*.jpg'):path.unlink(missing_ok=True);count+=1
                self.revision+=1
            return dict(cleared=count,message='只清理缩略图，原文件和整理信息保留；浏览时自动重建')
        if method=='analysis':
            action=a.get('action')
            if action=='install':return self.analyzer.install()
            if action=='resume':self.analyzer.paused=False
            if action=='pause':self.analyzer.paused=True
            if action=='rebuild':self.write("UPDATE photos SET analysis_status='pending',text_score=NULL WHERE kind='image'");self.write('DELETE FROM embeddings');self.analyzer.paused=False
            return self.analyzer.status()
        if method=='aiSearch':return self.analyzer.search(a)
        if method=='backup':return self.snapshot(a['path'])
        if method=='shutdown':
            self.closed=True;self.analyzer.closed=True;self.wake.set()
            following=getattr(self,'following_process',None)
            if following and following.poll() is None:following.terminate()
            health=getattr(self,'health_process',None)
            if health and health.poll() is None:health.terminate()
            self.avatar_pool.shutdown(wait=False,cancel_futures=True)
            if self.active:self.write("UPDATE tasks SET status='paused',message='软件已退出；已入库媒体保留，可继续' WHERE id=? AND status='running'",(self.active,))
            if self.process and self.process.poll() is None:self.process.terminate()
            return True
        raise ValueError('未知操作')
