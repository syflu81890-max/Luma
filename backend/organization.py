from collector_client import collector_command
"""Account collections, identity history, health pool and dashboard."""
import hashlib,json,subprocess,sys,threading,time,uuid
from pathlib import Path
from datetime import datetime,timezone,timedelta
from store import now,tags,json_text
from account_tools import AccountTools

class Organization(AccountTools):
    def observe_identity(self,ident,**override):
        rows=self.query('SELECT * FROM accounts WHERE id=?',(ident,))
        if not rows:return
        row={**rows[0],**override};handle=row['handle'];name=row['name'];url=row.get('avatar_url','');avatar=row.get('avatar_path','')
        if row.get('avatar_fetched_url') and row['avatar_fetched_url']!=url:avatar=''
        signature=hashlib.sha256(json_text([ident,handle,name,url,avatar,row.get('custom_avatar','')]).encode()).hexdigest()
        self.write('''INSERT INTO account_history(id,account,handle,name,avatar_url,avatar_path,custom_avatar,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,avatar_path=CASE WHEN excluded.avatar_path<>'' THEN excluded.avatar_path ELSE account_history.avatar_path END''',(signature,ident,handle,name,url,avatar,row.get('custom_avatar',''),now(),now()))
    def sync_collections(self,ident,value):
        names=tags(value)
        with self.transaction() as db:
            db.execute('DELETE FROM collection_members WHERE account=?',(ident,))
            for name in names:
                cid=hashlib.sha256(name.encode()).hexdigest()[:32]
                db.execute('INSERT OR IGNORE INTO account_collections(id,name,created) VALUES(?,?,?)',(cid,name,now()))
                actual=db.execute('SELECT id FROM account_collections WHERE name=?',(name,)).fetchone()[0]
                db.execute('INSERT OR IGNORE INTO collection_members VALUES(?,?)',(actual,ident))
    def collections(self):
        return self.query("SELECT c.*,COUNT(m.account) count,SUM(CASE WHEN ac.availability='suspended' THEN 1 ELSE 0 END) suspended FROM account_collections c LEFT JOIN collection_members m ON m.collection=c.id LEFT JOIN accounts ac ON ac.id=m.account GROUP BY c.id ORDER BY c.position,c.name COLLATE NOCASE")
    def collection_action(self,a):
        action=a['action']
        if action=='reorder':
            supplied=list(dict.fromkeys(a.get('ids',[])));existing=[r['id'] for r in self.collections()]
            if any(i not in existing for i in supplied):raise ValueError('合集列表已变化，请刷新后重试')
            with self.transaction() as db:
                for position,ident in enumerate(supplied+[i for i in existing if i not in supplied]):db.execute('UPDATE account_collections SET position=? WHERE id=?',(position,ident))
            return self.collections()
        if action=='create':
            name=str(a.get('name','')).strip()
            if not name or len(name)>80 or any(c in name for c in ',，\n'):raise ValueError('合集名称为 1–80 字，不含逗号或换行')
            ident=uuid.uuid4().hex;self.write('INSERT INTO account_collections(id,name,created) VALUES(?,?,?)',(ident,name,now()));return dict(id=ident,name=name)
        rows=self.query('SELECT * FROM account_collections WHERE id=?',(a['id'],))
        if not rows:raise ValueError('账号合集不存在')
        name=rows[0]['name']
        if action=='rename':
            new=str(a.get('name','')).strip()
            if not new or len(new)>80 or any(c in new for c in ',，\n'):raise ValueError('合集名称无效')
            if self.query('SELECT 1 FROM account_collections WHERE name=? AND id<>?',(new,a['id'])):raise ValueError('已有同名合集')
            members=self.query('SELECT ac.id,ac.categories FROM accounts ac JOIN collection_members m ON m.account=ac.id WHERE m.collection=?',(a['id'],))
            self.write('UPDATE account_collections SET name=? WHERE id=?',(new,a['id']))
            for member in members:self.save_account(dict(id=member['id'],categories=','.join(new if t==name else t for t in tags(member['categories']))))
        elif action in ('add','remove'):
            if action=='add':
                for ident in dict.fromkeys(a.get('ids',[])):
                    row=self.query('SELECT categories FROM accounts WHERE id=?',(ident,))
                    if row and name not in tags(row[0]['categories']) and len(tags(row[0]['categories']))>=3:raise ValueError('部分账号已有 3 个合集，请先移出一个合集再添加；未修改所选账号')
            for ident in dict.fromkeys(a.get('ids',[])):
                row=self.query('SELECT categories FROM accounts WHERE id=?',(ident,))
                if row:
                    old=tags(row[0]['categories']);self.save_account(dict(id=ident,categories=','.join(list(dict.fromkeys(old+[name])) if action=='add' else [n for n in old if n!=name])))
        else:raise ValueError('无效合集操作')
        return self.collections()
    def account_history(self,a):
        rows=self.query('SELECT * FROM account_history WHERE account=? ORDER BY first_seen DESC LIMIT 200',(a['id'],))
        photographed={(r['handle'],r['name'],r['avatar_url']) for r in rows if r['avatar_path'] or r['custom_avatar']}
        return [r for r in rows if r['avatar_path'] or r['custom_avatar'] or (r['handle'],r['name'],r['avatar_url']) not in photographed][:100]
    def set_account_health(self,ident,result):
        state=result.get('state','unknown');rows=self.query('SELECT availability FROM accounts WHERE id=?',(ident,))
        if not rows:return
        # An indeterminate retry must not release a suspended account from quarantine.
        effective=rows[0]['availability'] if state=='unknown' else state
        self.write('UPDATE accounts SET availability=?,availability_reason=?,availability_checked=? WHERE id=?',(effective,str(result.get('reason',''))[:500],now(),ident))
        if state=='suspended':
            self.write("UPDATE tasks SET status='blocked_account',message='平台明确返回账号封禁，已移入封禁池；下载好的内容保留',updated=? WHERE account=? AND status IN ('queued','running','waiting')",(now(),ident))
            active=self.query('SELECT account FROM tasks WHERE id=?',(self.active,)) if getattr(self,'active',None) else []
            if active and active[0]['account']==ident and self.process and self.process.poll() is None:self.process.terminate()
        elif state=='active' and rows[0]['availability']=='suspended':
            self.write("UPDATE tasks SET status='paused',message='账号已恢复正常；原任务保留，请在采集任务中选择恢复',updated=? WHERE account=? AND status='blocked_account'",(now(),ident))
        if state=='active' and result.get('profile'):
            profile=result['profile'];handle=profile.get('name') or self.account_detail(ident)['handle'];self.ensure_account(handle,profile)
    def health_status(self):return dict(getattr(self,'health_job',dict(status='idle',total=0,checked=0,restored=0,suspended=0,errors=[])))
    def start_health_check(self,a):
        if self.health_status()['status']=='running':return self.health_status()
        cookies=a.get('cookies') or self.session_cookies
        if not cookies.get('auth_token'):raise ValueError('请先登录 X 再检测账号；不会把未登录误判为封禁')
        ids=list(dict.fromkeys(a.get('ids') or [r['id'] for r in self.query("SELECT id FROM accounts WHERE availability='suspended'")]))
        if len(ids)>500:raise ValueError('每轮最多检测 500 个账号')
        self.health_job=dict(id=uuid.uuid4().hex,status='running',total=len(ids),checked=0,restored=0,suspended=0,errors=[],current='')
        self.busy_operations+=1
        def run():
            try:
                for ident in ids:
                    if self.closed:break
                    rows=self.query('SELECT id,handle,external_id,availability FROM accounts WHERE id=?',(ident,))
                    if not rows:continue
                    row=rows[0];self.health_job['current']='@'+row['handle']
                    command=collector_command('--probe-account')
                    try:
                        payload=dict(handle=row['handle'],external_id=row['external_id'],cookies=cookies,proxy=self.settings().get('proxy',''))
                        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.health_process=child
                        try:stdout,_=child.communicate(json_text(payload),timeout=60)
                        except subprocess.TimeoutExpired:child.kill();child.communicate();raise
                        finally:self.health_process=None
                        if self.closed:break
                        result=json.loads(stdout);self.set_account_health(ident,result)
                        if result['state']=='active' and row['availability']=='suspended':self.health_job['restored']+=1
                        elif result['state']=='suspended':self.health_job['suspended']+=1
                        elif result['state']=='unknown':self.health_job['errors'].append(dict(id=ident,message=result['reason']))
                    except Exception:self.health_job['errors'].append(dict(id=ident,message='检测暂未完成；原账号状态保留'))
                    self.health_job['checked']+=1
                    if not self.closed:time.sleep(1)
            finally:self.health_job.update(status='completed',current='');self.busy_operations-=1
        threading.Thread(target=run,daemon=True).start();return self.health_status()
    def dashboard(self):
        cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat();today=datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')
        accounts=self.query("SELECT COUNT(*) total,SUM(availability='suspended') suspended,SUM(availability<>'suspended' AND (last_checked='' OR last_checked<?)) stale,SUM(COALESCE(json_extract(schedule,'$.enabled'),0)=1 AND availability<>'suspended') scheduled FROM accounts",(cutoff,))[0]
        tasks={r['status']:r['n'] for r in self.query('SELECT status,COUNT(*) n FROM tasks WHERE hidden=0 GROUP BY status')}
        trend=self.query("SELECT date(created,'localtime') day,COUNT(*) count FROM photos WHERE created>=? GROUP BY day ORDER BY day",(cutoff,))
        return dict(accounts=accounts,tasks=tasks,trend=trend,todayAdded=next((r['count'] for r in trend if r['day']==today),0),recent=self.query("SELECT t.id,t.account,t.status,t.imported,t.updated,ac.handle,ac.alias,ac.name FROM tasks t LEFT JOIN accounts ac ON ac.id=t.account WHERE t.mode<>'import' ORDER BY t.updated DESC LIMIT 5"))
    def collect_all(self,a):
        filters=a.get('filters') or {};ids=self.account_rows({**filters,'pool':'normal'},True)
        return self.account_batch(dict(ids=ids,action='collect',cookies=a.get('cookies'),mode='latest'))
