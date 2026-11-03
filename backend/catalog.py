from collector_client import collector_command
"""Saved dynamic views, following imports and observable background work."""
import json,math,re,subprocess,sys,threading,uuid
from pathlib import Path
from store import now,json_text

class Catalog:
    def saved_views(self):
        return [dict(id=r['id'],name=r['name'],query=json.loads(r['query'])) for r in self.query('SELECT * FROM saved_views ORDER BY created')]

    def save_view(self,a):
        name=str(a.get('name','')).strip()
        if not name or len(name)>60:raise ValueError('视图名称为 1–60 字')
        query=a.get('query') or {};filters=query.get('filters') or {}
        allowed={'view','account','batch','album','q','tag','shape','kind','accountCategory','accountRating','sort','from','to','dateField','textFilter','textThreshold'}
        clean={k:v for k,v in filters.items() if k in allowed and isinstance(v,(str,int,float))}
        if len(json_text(clean))>5000:raise ValueError('筛选内容过长')
        value=dict(filters=clean,semantic=bool(query.get('semantic')),text=str(query.get('text',''))[:500])
        ident=uuid.uuid4().hex
        self.write('INSERT INTO saved_views VALUES(?,?,?,?)',(ident,name,json_text(value),now()))
        return self.saved_views()

    def background_status(self):
        return dict(analysis=self.analyzer.status(),similar=self.similar_status(),health=self.health_status(),following=self.following_status(),storage=self.storage_status(),active=self.active)

    def remember_accounts(self,ids):
        rows=[]
        for ident in dict.fromkeys(ids):
            rows.extend(self.query('SELECT id,alias,note,categories,rating,country,pinned_avatar FROM accounts WHERE id=?',(ident,)))
        if rows:self.write('INSERT INTO undo VALUES(?,?,?)',(uuid.uuid4().hex,now(),json_text(dict(kind='accounts',items=rows))))

    def following_status(self,a=None):
        a=a or {}
        rows=self.query('SELECT * FROM following_runs WHERE id=?',(a['id'],)) if a.get('id') else self.query('SELECT * FROM following_runs ORDER BY created DESC LIMIT 1')
        if not rows:return dict(status='idle',total=0,message='读取当前登录账号的关注列表')
        row=rows[0];row['total']=self.query('SELECT COUNT(*) n FROM following_users WHERE run=?',(row['id'],))[0]['n']
        return row

    def following_page(self,a):
        state=self.following_status(a)
        if not state.get('id'):return dict(items=[],total=0,pages=1,page=1,state=state)
        base=" FROM following_users u LEFT JOIN accounts ac ON ac.id=COALESCE((SELECT a.id FROM accounts a WHERE a.external_id=u.external_id LIMIT 1),(SELECT a.id FROM accounts a WHERE a.handle=u.handle COLLATE NOCASE LIMIT 1)) WHERE u.run=?"
        args=[state['id']]
        if a.get('q'):base+=' AND (u.handle LIKE ? OR u.name LIKE ?)';args+=['%'+str(a['q'])+'%']*2
        if a.get('onlyNew'):base+=' AND ac.id IS NULL'
        total=self.query('SELECT COUNT(*) n'+base,args)[0]['n'];size=100;pages=max(1,math.ceil(total/size));page=min(pages,max(1,int(a.get('page',1))))
        fields="u.*,ac.id account,ac.availability,EXISTS(SELECT 1 FROM tasks t WHERE t.account=ac.id AND t.status IN ('queued','running','waiting')) queued"
        return dict(items=self.query('SELECT '+fields+base+' ORDER BY u.name,u.handle LIMIT ? OFFSET ?',(*args,size,(page-1)*size)),total=total,pages=pages,page=page,state=state)

    def start_following(self,a):
        with self.lock:return self._start_following(a)

    def _start_following(self,a):
        if getattr(self,'following_job_running',False):raise ValueError('关注列表正在读取，请等待或暂停')
        owner=str(a.get('owner','')).lstrip('@')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}',owner):raise ValueError('请先验证当前 X 登录身份，或填写自己的账号名')
        cookies=a.get('cookies') or self.session_cookies
        if not cookies.get('auth_token'):raise ValueError('请先在软件中登录 X')
        previous=self.following_status(dict(id=a['resume'])) if a.get('resume') else {}
        if previous and previous.get('owner','').lower()!=owner.lower():raise ValueError('登录身份与上次读取不一致，请重新读取')
        ident=previous.get('id') or uuid.uuid4().hex
        if previous.get('status')=='completed':raise ValueError('上次读取已完整完成，请选择重新读取')
        if not previous:self.write('INSERT INTO following_runs(id,owner,created,updated,status) VALUES(?,?,?,?,?)',(ident,owner,now(),now(),'running'))
        else:self.write("UPDATE following_runs SET status='running',updated=?,message='继续读取，已读取结果保留' WHERE id=?",(now(),ident))
        self.following_job_running=True;self.following_cancelled=False;self.busy_operations+=1
        def run():
            child=None;finished=False
            try:
                command=collector_command('--following')
                child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.following_process=child
                if self.following_cancelled or self.closed:
                    child.terminate();self.write("UPDATE following_runs SET status='interrupted',message='读取已暂停，已读取结果保留',updated=? WHERE id=?",(now(),ident));return
                payload=dict(owner=owner,cookies=cookies,cursor=previous.get('cursor',''),proxy=self.settings().get('proxy',''))
                child.stdin.write(json_text(payload));child.stdin.close()
                watchdog=threading.Timer(900,lambda:child.terminate() if child.poll() is None else None);watchdog.daemon=True;watchdog.start()
                try:
                    for line in child.stdout:
                        if self.following_cancelled or self.closed:child.terminate();break
                        event=json.loads(line)
                        if event['type']=='user':
                            user=event['user'];handle=str(user.get('name',''));uid=str(user.get('id',''))
                            if uid and re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle):self.write('INSERT OR REPLACE INTO following_users VALUES(?,?,?,?,?,?)',(ident,uid,handle,str(user.get('nick') or handle),str(user.get('profile_image','')),int(bool(user.get('protected')))))
                        elif event['type']=='cursor':self.write('UPDATE following_runs SET cursor=?,updated=? WHERE id=?',(event.get('cursor') or '',now(),ident))
                        elif event['type']=='finished':
                            finished=True;ok=event.get('ok',False)
                            self.write('UPDATE following_runs SET status=?,message=?,updated=? WHERE id=?',('completed' if ok else 'interrupted',event.get('message','')[:500],now(),ident))
                    child.wait(timeout=10)
                finally:watchdog.cancel()
                if not finished:self.write("UPDATE following_runs SET status='interrupted',message=?,updated=? WHERE id=?",('读取已暂停，已读取账号保留，可继续' if self.following_cancelled else '读取未完整结束，已读取账号保留；可继续或重新登录后读取',now(),ident))
            except Exception:
                self.write("UPDATE following_runs SET status='interrupted',message='读取中断，已读取结果保留，请检查网络和登录后继续',updated=? WHERE id=?",(now(),ident))
            finally:
                try:
                    if child:
                        if child.poll() is None:
                            child.terminate()
                            try:child.wait(timeout=10)
                            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
                        if child.stdout:child.stdout.close()
                        if child.stdin and not child.stdin.closed:child.stdin.close()
                finally:
                    with self.lock:self.following_process=None;self.following_job_running=False;self.busy_operations-=1
        threading.Thread(target=run,daemon=True).start();return self.following_status(dict(id=ident))

    def finish_browser(self,a):
        with self.lock:
            count=self.query('SELECT COUNT(*) n FROM candidates WHERE task=?',(a['id'],))[0]['n']
            message=f'浏览器页面发现 {count} 项媒体，可选择下载；此任务不会推进账号完整采集边界' if count else '浏览器页面未返回可采集媒体；请确认页面能看到图片，滚动加载后再试，并核对登录身份与关注权限'
            self.write("UPDATE tasks SET status=?,updated=?,message=?,reason_code=? WHERE id=? AND status='paused' AND json_extract(options,'$.browserSource') IS NOT NULL",('completed' if count else 'partial',now(),message,'' if count else 'browser_empty',a['id']))
            if getattr(self,'browser_capture',None)==a['id']:self.browser_capture=None;self.busy_operations-=1
            return True
    def import_following(self,a):
        state=self.following_status(dict(id=a['id']))
        if state.get('status')=='running':raise ValueError('请先暂停读取或等读取完成，再创建采集任务')
        rows=self.query('SELECT * FROM following_users WHERE run=?',(state.get('id',''),));selected=set(a.get('ids') or [])
        if a.get('q'):rows=[r for r in rows if str(a['q']).casefold() in (r['handle']+' '+r['name']).casefold()]
        if not a.get('all'):rows=[r for r in rows if r['external_id'] in selected]
        collection=None
        if a.get('collection'):
            found=self.query('SELECT * FROM account_collections WHERE id=?',(a['collection'],))
            if not found:raise ValueError('所选合集不存在')
            collection=found[0]
        result=dict(succeeded=0,skipped=0,errors=[])
        for row in rows:
            try:
                existing=self.query('SELECT id FROM accounts WHERE external_id=? OR handle=? COLLATE NOCASE',(row['external_id'],row['handle']))
                if existing and self.query("SELECT 1 FROM accounts WHERE id=? AND availability='suspended'",(existing[0]['id'],)):result['skipped']+=1;continue
                if a.get('onlyNew') and existing:result['skipped']+=1;continue
                aid=self.ensure_account(row['handle'],dict(id=row['external_id'],nick=row['name'],profile_image=row['avatar_url'],protected=bool(row['protected'])))
                if collection:self.collection_action(dict(action='add',id=collection['id'],ids=[aid]))
                task=self.add_task(dict(url='@'+row['handle'],mode=a.get('mode','latest'),limit=0,cookies=a.get('cookies')))
                result['skipped' if task.get('merged') else 'succeeded']+=1
            except Exception as exc:result['errors'].append(dict(id=row['handle'],message=str(exc)))
        return result
