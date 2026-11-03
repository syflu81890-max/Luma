"""Paginated management views and session-only completion barriers."""
import json,math,os,shutil,time
from datetime import datetime,timezone
from store import now,tags

ACTIVE=('queued','running','waiting')

class Management:
    def account_rows(self,a=None,ids_only=False):
        a=a or {};q='%'+str(a.get('q',''))+'%';clauses=['(ac.handle LIKE ? OR ac.alias LIKE ? OR ac.name LIKE ? OR ac.note LIKE ?)'];args=[q]*4
        pool=a.get('pool','normal')
        if pool=='suspended':clauses.append("ac.availability='suspended'")
        elif pool!='all':clauses.append("ac.availability<>'suspended'")
        if a.get('collection')=='unfiled':clauses.append("NOT EXISTS(SELECT 1 FROM collection_members cm WHERE cm.account=ac.id)")
        elif a.get('collection'):clauses.append("EXISTS(SELECT 1 FROM collection_members cm WHERE cm.account=ac.id AND cm.collection=?)");args.append(a['collection'])
        if a.get('category'):clauses.append("(','||ac.categories||',') LIKE ?");args.append('%,'+a['category']+',%')
        rating=str(a.get('rating') or 'all')
        if rating!='all':
            if rating=='unrated':clauses.append('ac.rating=0')
            elif rating.endswith('+'):clauses.append('ac.rating>=?');args.append(int(rating[:-1]))
            else:clauses.append('ac.rating=?');args.append(int(rating))
        if a.get('status'):
            if a['status']=='idle':clauses.append("(lt.status IS NULL OR lt.status IN ('completed','cancelled'))")
            else:clauses.append('lt.status=?');args.append(a['status'])
        if a.get('staleDays'):
            from datetime import timedelta
            clauses.append("(ac.last_checked='' OR ac.last_checked<?)");args.append((datetime.now(timezone.utc)-timedelta(days=int(a['staleDays']))).isoformat())
        if a.get('scheduled') in ('on','off'):
            clauses.append("COALESCE(json_extract(ac.schedule,'$.enabled'),0)=?");args.append(int(a['scheduled']=='on'))
        cte="""WITH ranked AS (SELECT t.*,ROW_NUMBER() OVER(PARTITION BY account ORDER BY CASE WHEN status IN ('queued','running','waiting') THEN 0 ELSE 1 END,created DESC,id DESC) rn FROM tasks t WHERE account<>''),
          media_stats AS (SELECT * FROM account_media_stats),
          task_stats AS (SELECT account,COUNT(*) batches,MAX(CASE WHEN imported>0 THEN created END) last_added FROM tasks GROUP BY account) """
        joins=" FROM accounts ac LEFT JOIN ranked lt ON lt.account=ac.id AND lt.rn=1 LEFT JOIN media_stats ms ON ms.account=ac.id LEFT JOIN task_stats ts ON ts.account=ac.id "
        where=' WHERE '+' AND '.join(clauses)
        sorts={'new':'ac.created','name':"COALESCE(NULLIF(ac.alias,''),NULLIF(ac.name,''),ac.handle) COLLATE NOCASE",'rating':'ac.rating','count':'COALESCE(ms.retained,0)','checked':'ac.last_checked','next':'ac.next_run','added':'ts.last_added'}
        direction='ASC' if a.get('direction')=='asc' else 'DESC';order=sorts.get(a.get('sort'),'ac.created')+' '+direction+',ac.id ASC'
        if ids_only:return [r['id'] for r in self.query(cte+'SELECT ac.id'+joins+where+' ORDER BY '+order,args)]
        size=int(a.get('limit',64));size=size if size in (24,32,50,64,96,100,128,200) else 64
        total=self.query(cte+'SELECT COUNT(*) n'+joins+where,args)[0]['n'];pages=max(1,math.ceil(total/size));page=min(pages,max(1,int(a.get('page',1))))
        fields="ac.*,COALESCE(ms.retained,0) retained,COALESCE(ms.deleted,0) deleted,COALESCE(ms.images,0) images,COALESCE(ms.videos,0) videos,COALESCE(ms.gifs,0) gifs,COALESCE(ms.storage,0) storage,COALESCE(ts.batches,0) batches,ts.last_added,lt.id task_id,lt.status task_status,lt.imported last_imported,lt.created task_created,lt.mode task_mode"
        items=self.query(cte+'SELECT '+fields+joins+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*args,size,(page-1)*size))
        pools=self.query("SELECT SUM(availability='suspended') suspended,SUM(availability<>'suspended') normal FROM accounts")[0]
        return dict(items=items,total=total,pages=pages,page=page,limit=size,pools=pools)

    def task_page(self,a=None,ids_only=False):
        a=a or {};where=['t.hidden=0'];args=[];status=a.get('status','active')
        if status=='active':where.append("t.status IN ('queued','running','waiting')")
        elif status=='attention':where.append("t.status IN ('failed','needs_login','needs_access','paused','partial','blocked_account')")
        elif status and status!='all':where.append('t.status=?');args.append(status)
        if a.get('q'):where.append('(t.url LIKE ? OR ac.alias LIKE ? OR ac.handle LIKE ?)');args.extend(['%'+str(a['q'])+'%']*3)
        if a.get('account'):where.append('t.account=?');args.append(a['account'])
        base=' FROM tasks t LEFT JOIN accounts ac ON ac.id=t.account WHERE '+' AND '.join(where)
        order=" ORDER BY CASE t.status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'waiting' THEN 2 ELSE 3 END,t.created DESC,t.id ASC"
        if ids_only:return [r['id'] for r in self.query('SELECT t.id'+base+order,args)]
        size=int(a.get('limit',100));size=size if size in (50,100,200) else 100
        total=self.query('SELECT COUNT(*) n'+base,args)[0]['n'];pages=max(1,math.ceil(total/size));page=min(pages,max(1,int(a.get('page',1))))
        items=self.query('SELECT t.*,ac.handle,ac.alias,ac.name'+base+order+' LIMIT ? OFFSET ?',(*args,size,(page-1)*size))
        counts={r['status']:r['n'] for r in self.query('SELECT status,COUNT(*) n FROM tasks WHERE hidden=0 GROUP BY status')}
        return dict(items=items,total=total,pages=pages,page=page,limit=size,counts=counts)

    def account_batch(self,a):
        action=a['action'];result=dict(succeeded=0,skipped=0,errors=[])
        for ident in dict.fromkeys(a.get('ids',[])):
            try:
                row=self.account_detail(ident)
                if action=='collect':
                    task=self.add_task(dict(url='@'+row['handle'],limit=0,mode=a.get('mode','latest'),cookies=a.get('cookies')))
                    if task.get('merged'):result['skipped']+=1;continue
                elif action=='pause':
                    tasks=self.query("SELECT id FROM tasks WHERE account=? AND status IN ('queued','running','waiting')",(ident,))
                    for task in tasks:self.task_action(dict(id=task['id'],action='pause'))
                    self.write('UPDATE accounts SET auto_paused=1 WHERE id=?',(ident,))
                elif action=='rating':self.save_account(dict(id=ident,rating=a['rating']))
                elif action=='categories':
                    old=tags(row['categories']);new=tags(a.get('categories',''));mode=a.get('tagMode','add')
                    self.save_account(dict(id=ident,categories=','.join([x for x in old if x not in new] if mode=='remove' else new if mode=='replace' else list(dict.fromkeys(old+new)))))
                elif action=='schedule':self.schedule(dict(id=ident,rule=a['rule']))
                elif action=='scheduleToggle':
                    rule=json.loads(row['schedule'] or '{}');rule['enabled']=bool(a['enabled']);self.schedule(dict(id=ident,rule=rule))
                else:raise ValueError('未知账号批量操作')
                result['succeeded']+=1
            except Exception as exc:result['errors'].append(dict(id=ident,message=str(exc)))
        return result

    def task_batch(self,a):
        result=dict(succeeded=0,skipped=0,errors=[]);action=a['action']
        for ident in dict.fromkeys(a.get('ids',[])):
            try:
                rows=self.query('SELECT * FROM tasks WHERE id=?',(ident,))
                if not rows:result['skipped']+=1;continue
                t=rows[0]
                if action=='hide':
                    if t['status'] not in ('completed','cancelled'):result['skipped']+=1;continue
                    self.write('UPDATE tasks SET hidden=1 WHERE id=?',(ident,))
                else:
                    allowed={'pause':ACTIVE,'resume':('paused','partial','failed','needs_login','needs_access','cancelled'),'retryFailed':('failed','needs_login','needs_access'),'cancel':('queued','running','waiting','paused','partial','failed','needs_login','needs_access')}
                    if t['status'] not in allowed.get(action,()):result['skipped']+=1;continue
                    self.task_action(dict(id=ident,action='resume' if action=='retryFailed' else action,cookies=a.get('cookies')))
                result['succeeded']+=1
            except Exception as exc:result['errors'].append(dict(id=ident,message=str(exc)))
        return result

    def completion(self,a):
        action=a.get('action','status')
        with self.lock:
            if action=='arm':
                if self.maintenance or self.completion_frozen:raise ValueError('资料库正在维护，暂不能设置完成后动作')
                ids={r['id'] for r in self.query("SELECT id FROM tasks WHERE status IN ('queued','running','waiting')")}
                if not ids:raise ValueError('请先添加正在运行或排队的采集任务')
                self.completion_ids=ids;self.completion_hold=True;self.completion_interrupted='';self.completion_wait_analysis=bool(a.get('waitAnalysis'))
            if action=='cancel':
                if self.completion_frozen:self.maintenance=False
                self.completion_hold=False;self.completion_frozen=False;self.completion_ids=set();self.completion_interrupted=''
                if getattr(self,'completion_restore_analysis',False):self.analyzer.paused=False
                self.completion_restore_analysis=False;self.wake.set()
                return dict(armed=False)
            if not self.completion_hold:return dict(armed=False)
            rows=self.query('SELECT id,status,mode FROM tasks WHERE id IN ('+','.join('?' for _ in self.completion_ids)+')',tuple(self.completion_ids))
            reason=self.completion_interrupted
            if not reason:
                blocked=next((r for r in rows if r['status'] in ('failed','needs_login','needs_access','paused','cancelled','partial','blocked_account')),None)
                if blocked:reason='本轮存在失败、暂停、待补齐或取消的任务，请处理后重新启用'
                if any(r['mode']=='preview' and r['status']=='completed' for r in rows):reason='预览任务已结束，请先勾选需要下载的媒体，再重新启用'
            complete=bool(rows) and len(rows)==len(self.completion_ids) and all(r['status']=='completed' for r in rows)
            storage=self.storage_status()
            if storage['errors']:reason='磁盘目录整理遇到问题，请在设置中处理后重新启用'
            analysis=self.analyzer.status()
            busy=storage['pending']>0 or self.active is not None or self.busy_operations>0 or self.analyzer.downloading or self.maintenance and not self.completion_frozen
            if complete and self.completion_wait_analysis:
                if analysis['error']:reason='本地分析遇到问题，请处理后重新启用'
                pending=analysis['pending']>0 or (analysis['modelReady'] and analysis['indexed']<self.query("SELECT COUNT(*) n FROM photos WHERE trash=0 AND kind='image'")[0]['n'])
                if pending and self.analyzer.paused:reason='本地分析已暂停，请继续分析或取消等待分析'
                busy=busy or pending or self.analyzer.busy
            ready=complete and not busy and not reason
            if action=='prepare':
                if not ready:raise ValueError(reason or '仍有任务或写入操作，已停止完成后动作')
                if not self.completion_frozen:self.completion_restore_analysis=not self.analyzer.paused
                self.completion_frozen=True;self.maintenance=True;self.analyzer.paused=True
                if self.analyzer.busy:return dict(armed=True,ready=False,total=len(rows),reason='',preparing=True)
                self.db.execute('PRAGMA wal_checkpoint(FULL)');self.db.commit()
                with (self.root/'library.db').open('rb+') as f:os.fsync(f.fileno())
            return dict(armed=True,ready=ready,reason=reason,generation=self.completion_generation,total=len(rows),complete=sum(r['status']=='completed' for r in rows),busy=busy)
