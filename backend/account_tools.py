"""Account organization, explicit removal and language-based region suggestions."""
import collections,hashlib,json,re,uuid
from store import now,json_text,tags

# Suggestions only. Shared languages such as English do not imply nationality.
LANGUAGE_REGIONS={'ja':'JP','ko':'KR','zh':'CN','th':'TH','vi':'VN','id':'ID','uk':'UA','pl':'PL','tr':'TR','he':'IL','el':'GR','fi':'FI','sv':'SE','da':'DK','no':'NO','cs':'CZ','hu':'HU','ro':'RO'}

class AccountTools:
    def note_presets(self):
        rows=self.query('SELECT text,uses FROM note_presets ORDER BY uses DESC,updated DESC LIMIT 8')
        if not rows:rows=self.query("SELECT note text,COUNT(*) uses FROM accounts WHERE note<>'' AND length(note)<=240 GROUP BY note ORDER BY uses DESC,MAX(created) DESC LIMIT 8")
        return rows

    def remember_note(self,text):
        text=str(text).strip()
        if text and len(text)<=240:self.write('INSERT INTO note_presets VALUES(?,1,?) ON CONFLICT(text) DO UPDATE SET uses=uses+1,updated=excluded.updated',(text,now()))

    def infer_account_region(self,ident):
        rows=self.query('SELECT metadata FROM sources WHERE account=? ORDER BY published DESC LIMIT 300',(ident,));posts={}
        for row in rows:
            try:meta=json.loads(row['metadata']);post=str(meta.get('tweet_id') or meta.get('post_id') or '')
            except (ValueError,TypeError):continue
            language=str(meta.get('lang') or meta.get('language') or '').lower().replace('_','-')
            if post and language and language not in ('und','zxx'):posts[post]=language
        counts=collections.Counter(posts.values());language=counts.most_common(1)[0][0] if counts else ''
        code=LANGUAGE_REGIONS.get(language.split('-')[0],'')
        if language in ('zh-tw','zh-hk','zh-cn'):code=language.split('-')[1].upper()
        self.write('UPDATE accounts SET suggested_country=?,country_language=?,language_checked=? WHERE id=?',(code,language,now(),ident))
        return dict(country=code,language=language,suggested=True)

    def region_backfill(self):
        for row in self.query("SELECT id FROM accounts WHERE language_checked='' LIMIT 2"):
            if self.closed or self.maintenance:break
            self.infer_account_region(row['id'])

    def account_remove_plan(self,a):
        account=self.account_detail(a['id'])
        exclusive=[r['photo'] for r in self.query('SELECT ap.photo FROM account_photos ap WHERE ap.account=? AND NOT EXISTS(SELECT 1 FROM account_photos other WHERE other.photo=ap.photo AND other.account<>?)',(a['id'],a['id']))]
        total=self.query('SELECT COUNT(*) n FROM account_photos WHERE account=?',(a['id'],))[0]['n']
        return dict(id=account['id'],handle=account['handle'],media=total,exclusive=len(exclusive),shared=total-len(exclusive),tasks=len(self.query('SELECT id FROM tasks WHERE account=?',(a['id'],))),history=len(self.account_history(a)),exclusiveIds=exclusive)

    def remove_account(self,a):
        with self.lock:return self._remove_account(a)

    def _remove_account(self,a):
        ident=a['id'];plan=self.account_remove_plan(a)
        if str(a.get('confirmHandle','')).lstrip('@').casefold()!=plan['handle'].casefold():raise ValueError('请完整输入账号名确认删除')
        if self.active and self.query('SELECT 1 FROM tasks WHERE id=? AND account=?',(self.active,ident)):raise ValueError('请先暂停此账号正在运行的采集任务')
        if self.health_status()['status']=='running' or getattr(self,'following_job_running',False) or getattr(self,'browser_capture',None):raise ValueError('请先结束账号检测、关注读取或浏览器补采')
        if ident in self.avatar_requested:raise ValueError('头像正在保存，请稍后删除账号')
        tables={name:self.query('SELECT * FROM '+name+' WHERE '+column+'=?',(ident,)) for name,column in [('accounts','id'),('account_photos','account'),('sources','account'),('tasks','account'),('account_history','account'),('collection_members','account')]}
        task_ids=[r['id'] for r in tables['tasks']]
        tables['task_items']=[row for task in task_ids for row in self.query('SELECT * FROM task_items WHERE task=?',(task,))]
        tables['candidates']=[row for task in task_ids for row in self.query('SELECT * FROM candidates WHERE task=?',(task,))]
        photos=self.query('SELECT p.id,p.trash,p.author FROM photos p JOIN account_photos ap ON ap.photo=p.id WHERE ap.account=? AND NOT EXISTS(SELECT 1 FROM account_photos other WHERE other.photo=p.id AND other.account<>?)',(ident,ident))
        undo=uuid.uuid4().hex;trash=bool(a.get('trashExclusive',True))
        with self.transaction() as db:
            if trash:
                for photo in photos:
                    if photo['trash']==0:
                        db.execute('UPDATE photos SET trash=1 WHERE id=?',(photo['id'],));db.execute('INSERT OR IGNORE INTO excluded_content VALUES(?,?)',(photo['id'],now()));db.execute('INSERT OR IGNORE INTO excluded_media SELECT media_key,photo,? FROM media WHERE photo=?',(now(),photo['id']))
            for task in task_ids:
                db.execute('DELETE FROM task_items WHERE task=?',(task,));db.execute('DELETE FROM candidates WHERE task=?',(task,))
            for name,column in [('account_photos','account'),('sources','account'),('tasks','account'),('account_history','account'),('collection_members','account'),('account_media_stats','account'),('accounts','id')]:db.execute('DELETE FROM '+name+' WHERE '+column+'=?',(ident,))
            for photo in photos:db.execute("UPDATE photos SET author='' WHERE id=? AND author=?",(photo['id'],plan['handle']))
            db.execute('INSERT INTO undo VALUES(?,?,?)',(undo,now(),json_text(dict(kind='removedAccount',account=ident,tables=tables,photos=photos))))
        for row in tables['account_photos']:self.mark_layout(row['photo'])
        return dict(removed=True,undo=undo,trashed=len([p for p in photos if p['trash']==0]) if trash else 0,sharedRetained=plan['shared'])

    def restore_removed_account(self,payload):
        first=payload['tables']['accounts'][0]
        if self.query('SELECT 1 FROM accounts WHERE id=? OR handle=?',(first['id'],first['handle'])):raise ValueError('同名账号已重新添加，请先处理冲突；未覆盖现有账号')
        with self.transaction() as db:
            for table in ('accounts','tasks','account_photos','sources','account_history','collection_members','task_items','candidates'):
                for row in payload['tables'][table]:
                    row=dict(row)
                    if table=='tasks' and row['status'] in ('queued','running','waiting'):row.update(status='paused',message='账号已恢复，任务暂停待手动继续')
                    names=list(row);db.execute('INSERT OR IGNORE INTO '+table+'('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',tuple(row.values()))
            for row in payload['photos']:
                current=db.execute('SELECT trash FROM photos WHERE id=?',(row['id'],)).fetchone()
                if current and current['trash']!=2:
                    db.execute('UPDATE photos SET trash=?,author=? WHERE id=?',(row['trash'],row['author'],row['id']))
                    if row['trash']==0:db.execute('DELETE FROM excluded_content WHERE photo=?',(row['id'],));db.execute('DELETE FROM excluded_media WHERE photo=?',(row['id'],))
        for row in payload['tables']['account_photos']:self.mark_layout(row['photo'])
