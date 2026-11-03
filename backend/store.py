"""Versioned, crash-recoverable local library. No network or UI dependencies."""
import base64, hashlib, io, json, math, os, re, shutil, sqlite3, threading, time, uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager,closing
from urllib.parse import urlparse
from PIL import Image, ImageOps
from media_utils import inspect_media,VIDEO_EXT
from storage_layout import StorageLayout

EXT={'.jpg','.jpeg','.png','.webp','.gif','.bmp'}|VIDEO_EXT
def now():return datetime.now(timezone.utc).isoformat()
def json_text(value):return json.dumps(value,ensure_ascii=False,default=str)
def tags(value):return list(dict.fromkeys(t.strip() for t in re.split('[,，\n]',str(value)) if t.strip()))
def normalize(value):
    value=str(value).strip()
    if re.fullmatch(r'@?[A-Za-z0-9_]{1,15}',value):value='https://x.com/'+value.lstrip('@')+'/media'
    u=urlparse(value)
    if u.scheme!='https' or u.hostname not in {'x.com','www.x.com','twitter.com','www.twitter.com'} or u.username or u.password or u.port not in (None,443):raise ValueError('请输入 X 账号或 https://x.com/ 链接')
    if not u.path.strip('/'):raise ValueError('请输入账号主页或帖子链接')
    handle=u.path.strip('/').split('/')[0]
    if handle.lower() in {'i','search','home','explore','settings'}:
        if not re.search(r'/status/\d+',u.path):raise ValueError('本版支持账号和帖子链接，请勿输入搜索页或首页')
    return 'https://x.com'+u.path.rstrip('/')
def handle_from_url(url):
    handle=urlparse(url).path.strip('/').split('/')[0]
    return handle if re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle) and handle!='i' else ''
def media_info(metadata,url=''):
    m=metadata or {};author=m.get('author') or {};author=author if isinstance(author,dict) else {}
    post=str(m.get('tweet_id') or m.get('post_id') or '')
    if not post:
        found=re.search(r'/status/(\d+)',url);post=found[1] if found else ''
    index=str(m.get('num') or 1);key=f'{post}:{index}' if post else ''
    return post,key,author
def atomic_copy(source,destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_name(destination.name+'.pending-'+uuid.uuid4().hex[:8])
    try:
        shutil.copy2(source,temp)
        with temp.open('rb+') as f:os.fsync(f.fileno())
        os.replace(temp,destination)
    finally:temp.unlink(missing_ok=True)
def visual_hash(im):
    pixels=list(im.convert('L').resize((9,8)).getdata());value=0
    for y in range(8):
        for x in range(8):value=(value<<1)|int(pixels[y*9+x]>pixels[y*9+x+1])
    return f'{value:016x}'

from organization import Organization

class Store(Organization,StorageLayout):
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        for d in ['originals','thumbs','staging','avatars','backups','edits','models']:(self.root/d).mkdir(exist_ok=True)
        self.lock=threading.RLock();self.db=sqlite3.connect(self.root/'library.db',check_same_thread=False,timeout=30);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA busy_timeout=30000');self.db.execute('PRAGMA journal_mode=WAL')
        self.revision=0;self._migrate()
    def query(self,sql,args=()):
        with self.lock:return [dict(r) for r in self.db.execute(sql,args).fetchall()]
    def write(self,sql,args=()):
        with self.lock:self.db.execute(sql,args);self.db.commit();self.revision+=1
    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                self.db.execute('BEGIN IMMEDIATE');yield self.db;self.db.commit();self.revision+=1
            except Exception:self.db.rollback();raise
    def _migrate(self):
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        legacy=bool(self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='photos'").fetchone())
        if version>6:raise ValueError('此资料库由更新版本创建，请使用新版 Luma；未修改资料库')
        if legacy and version<6:
            with closing(sqlite3.connect(self.root/'backups'/('before-v6-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db'))) as out:self.db.backup(out)
        if legacy and version<5:
            with closing(sqlite3.connect(self.root/'backups'/('before-v5-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db'))) as out:self.db.backup(out)
        if legacy and version<4:
            with closing(sqlite3.connect(self.root/'backups'/('before-v4-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db'))) as out:self.db.backup(out)
        if legacy and version<2:
            backup=self.root/'backups'/('before-v2-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
            with closing(sqlite3.connect(backup)) as out:self.db.backup(out)
        if legacy and version==2:
            with closing(sqlite3.connect(self.root/'backups'/('before-v3-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db'))) as out:self.db.backup(out)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY,path TEXT,width INT,height INT,size INT,created TEXT,tags TEXT DEFAULT '',favorite INT DEFAULT 0,trash INT DEFAULT 0,note TEXT DEFAULT '',color TEXT,author TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sources(photo TEXT,url TEXT,metadata TEXT,UNIQUE(photo,url));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,url TEXT,limit_count INT,status TEXT,created TEXT,message TEXT DEFAULT '',imported INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,handle TEXT COLLATE NOCASE UNIQUE,name TEXT DEFAULT '',alias TEXT DEFAULT '',note TEXT DEFAULT '',avatar_url TEXT DEFAULT '',avatar_path TEXT DEFAULT '',custom_avatar TEXT DEFAULT '',created TEXT,last_checked TEXT DEFAULT '',watermark TEXT DEFAULT '0',pending_top TEXT DEFAULT '0',schedule TEXT DEFAULT '{}',next_run TEXT DEFAULT '',auto_paused INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS account_photos(account TEXT,photo TEXT,first_seen TEXT,PRIMARY KEY(account,photo));
        CREATE TABLE IF NOT EXISTS media(media_key TEXT PRIMARY KEY,photo TEXT,post_id TEXT,metadata TEXT);
        CREATE TABLE IF NOT EXISTS excluded_content(photo TEXT PRIMARY KEY,created TEXT);
        CREATE TABLE IF NOT EXISTS excluded_media(media_key TEXT PRIMARY KEY,photo TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS task_items(task TEXT,media_key TEXT,photo TEXT,outcome TEXT,seen TEXT,PRIMARY KEY(task,media_key));
        CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY,name TEXT UNIQUE,created TEXT);
        CREATE TABLE IF NOT EXISTS album_photos(album TEXT,photo TEXT,PRIMARY KEY(album,photo));
        CREATE TABLE IF NOT EXISTS embeddings(photo TEXT,model TEXT,vector BLOB,PRIMARY KEY(photo,model));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS media_locations(photo TEXT,path TEXT UNIQUE,PRIMARY KEY(photo,path));
        CREATE TABLE IF NOT EXISTS layout_jobs(photo TEXT PRIMARY KEY,error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS candidates(task TEXT,media_key TEXT,url TEXT,metadata TEXT,PRIMARY KEY(task,media_key));
        CREATE TABLE IF NOT EXISTS undo(id TEXT PRIMARY KEY,created TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS saved_views(id TEXT PRIMARY KEY,name TEXT UNIQUE,query TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS following_runs(id TEXT PRIMARY KEY,owner TEXT,created TEXT,updated TEXT,status TEXT,cursor TEXT DEFAULT '',message TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS following_users(run TEXT,external_id TEXT,handle TEXT,name TEXT,avatar_url TEXT,protected INT DEFAULT 0,PRIMARY KEY(run,external_id));
        CREATE TABLE IF NOT EXISTS account_collections(id TEXT PRIMARY KEY,name TEXT UNIQUE,created TEXT);
        CREATE TABLE IF NOT EXISTS collection_members(collection TEXT,account TEXT,PRIMARY KEY(collection,account));
        CREATE INDEX IF NOT EXISTS ix_collection_account ON collection_members(account,collection);
        CREATE TABLE IF NOT EXISTS account_history(id TEXT PRIMARY KEY,account TEXT,handle TEXT,name TEXT,avatar_url TEXT,avatar_path TEXT,custom_avatar TEXT,first_seen TEXT,last_seen TEXT);
        CREATE INDEX IF NOT EXISTS ix_account_history ON account_history(account,first_seen DESC);
        CREATE INDEX IF NOT EXISTS ix_account_photos_photo ON account_photos(photo);
        CREATE INDEX IF NOT EXISTS ix_task_items_photo ON task_items(photo);
        CREATE INDEX IF NOT EXISTS ix_task_items_task ON task_items(task);
        CREATE INDEX IF NOT EXISTS ix_media_photo ON media(photo);
        ''')
        additions={
            'accounts':{'external_id':"TEXT DEFAULT ''",'rating':'INT DEFAULT 0','categories':"TEXT DEFAULT ''",'availability':"TEXT DEFAULT 'unknown'",'availability_reason':"TEXT DEFAULT ''",'availability_checked':"TEXT DEFAULT ''",'avatar_fetched_url':"TEXT DEFAULT ''",'last_success':"TEXT DEFAULT ''",'last_published':"TEXT DEFAULT ''",'protected':'INT DEFAULT 0'},
            'photos':{'format':"TEXT DEFAULT ''",'kind':"TEXT DEFAULT 'image'",'duration':'REAL DEFAULT 0','phash':"TEXT DEFAULT ''",'text_score':'REAL','ocr_text':"TEXT DEFAULT ''",'analysis_status':"TEXT DEFAULT 'pending'",'reviewed':'INT DEFAULT 0','parent':"TEXT DEFAULT ''"},
            'sources':{'account':"TEXT DEFAULT ''",'post_id':"TEXT DEFAULT ''",'published':"TEXT DEFAULT ''",'content':"TEXT DEFAULT ''"},
            'tasks':{'account':"TEXT DEFAULT ''",'mode':"TEXT DEFAULT 'latest'",'options':"TEXT DEFAULT '{}'",'updated':"TEXT DEFAULT ''",'duplicates':'INT DEFAULT 0','excluded':'INT DEFAULT 0','failed':'INT DEFAULT 0','scanned':'INT DEFAULT 0','retry_at':"TEXT DEFAULT ''",'attempt':'INT DEFAULT 0','origin':"TEXT DEFAULT 'manual'",'capped':'INT DEFAULT 0','hidden':'INT DEFAULT 0','started':"TEXT DEFAULT ''",'elapsed':'REAL DEFAULT 0','downloaded_bytes':'INT DEFAULT 0','speed':'REAL DEFAULT 0','result_json':"TEXT DEFAULT '{}'",'reason_code':"TEXT DEFAULT ''"}
        }
        for table,columns in additions.items():
            known={r[1] for r in self.db.execute(f'PRAGMA table_info({table})')}
            for name,definition in columns.items():
                if name not in known:self.db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_sources_account ON sources(account,photo)');self.db.execute('CREATE INDEX IF NOT EXISTS ix_photos_page ON photos(trash,created,id)')
        self.db.commit()
        if version<2:
            # Old task counters cannot be reconstructed exactly: keep them as legacy batches.
            for t in self.query('SELECT * FROM tasks'):
                handle=handle_from_url(t['url']) if t['url'].startswith('https:') else ''
                if handle:self.write("UPDATE tasks SET account=?,mode='legacy' WHERE id=?",(self.ensure_account(handle),t['id']))
            for p in self.query('SELECT id,path,author,trash FROM photos'):
                old=Path(p['path']);relative=Path('originals')/old.name
                if (self.root/relative).exists():self.write('UPDATE photos SET path=? WHERE id=?',(relative.as_posix(),p['id']))
                if p['author']:
                    aid=self.ensure_account(p['author']);self.write('INSERT OR IGNORE INTO account_photos VALUES(?,?,?)',(aid,p['id'],now()))
                if p['trash']:self.write('INSERT OR IGNORE INTO excluded_content VALUES(?,?)',(p['id'],now()))
            for s in self.query('SELECT * FROM sources'):
                try:m=json.loads(s['metadata'] or '{}')
                except ValueError:m={}
                self._source(s['photo'],s['url'],m)
            self.write('INSERT OR IGNORE INTO excluded_media SELECT m.media_key,m.photo,? FROM media m JOIN excluded_content e ON e.photo=m.photo',(now(),))
            self.db.execute('PRAGMA user_version=2');self.db.commit()
        if not self.query("SELECT 1 FROM settings WHERE key='storageLayoutVersion' AND value='1'"):
            self.db.execute("INSERT OR IGNORE INTO layout_jobs(photo) SELECT id FROM photos WHERE trash<>2");self.db.execute("INSERT OR REPLACE INTO settings VALUES('storageLayoutVersion','1')");self.db.commit()
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_tasks_account_created ON tasks(account,created DESC,id)');self.db.execute('CREATE INDEX IF NOT EXISTS ix_tasks_status_created ON tasks(status,created DESC)');self.db.execute('CREATE INDEX IF NOT EXISTS ix_sources_photo_published ON sources(photo,published DESC)');self.db.execute('CREATE INDEX IF NOT EXISTS ix_photos_kind_trash ON photos(trash,kind)');self.db.commit()
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS account_media_stats(account TEXT PRIMARY KEY,retained INT DEFAULT 0,deleted INT DEFAULT 0,images INT DEFAULT 0,videos INT DEFAULT 0,gifs INT DEFAULT 0,storage INT DEFAULT 0);
        CREATE TRIGGER IF NOT EXISTS account_media_insert AFTER INSERT ON account_photos BEGIN
          INSERT INTO account_media_stats SELECT NEW.account,p.trash=0,p.trash<>0,p.trash=0 AND p.kind='image',p.trash=0 AND p.kind='video',p.trash=0 AND p.kind='gif',CASE WHEN p.trash=0 THEN p.size ELSE 0 END FROM photos p WHERE p.id=NEW.photo
          ON CONFLICT(account) DO UPDATE SET retained=retained+excluded.retained,deleted=deleted+excluded.deleted,images=images+excluded.images,videos=videos+excluded.videos,gifs=gifs+excluded.gifs,storage=storage+excluded.storage;
        END;
        CREATE TRIGGER IF NOT EXISTS account_media_remove AFTER DELETE ON account_photos BEGIN
          UPDATE account_media_stats SET retained=retained-COALESCE((SELECT trash=0 FROM photos WHERE id=OLD.photo),0),deleted=deleted-COALESCE((SELECT trash<>0 FROM photos WHERE id=OLD.photo),0),images=images-COALESCE((SELECT trash=0 AND kind='image' FROM photos WHERE id=OLD.photo),0),videos=videos-COALESCE((SELECT trash=0 AND kind='video' FROM photos WHERE id=OLD.photo),0),gifs=gifs-COALESCE((SELECT trash=0 AND kind='gif' FROM photos WHERE id=OLD.photo),0),storage=storage-COALESCE((SELECT CASE WHEN trash=0 THEN size ELSE 0 END FROM photos WHERE id=OLD.photo),0) WHERE account=OLD.account;
        END;
        CREATE TRIGGER IF NOT EXISTS account_media_update AFTER UPDATE OF trash,kind,size ON photos BEGIN
          UPDATE account_media_stats SET retained=retained+(NEW.trash=0)-(OLD.trash=0),deleted=deleted+(NEW.trash<>0)-(OLD.trash<>0),images=images+(NEW.trash=0 AND NEW.kind='image')-(OLD.trash=0 AND OLD.kind='image'),videos=videos+(NEW.trash=0 AND NEW.kind='video')-(OLD.trash=0 AND OLD.kind='video'),gifs=gifs+(NEW.trash=0 AND NEW.kind='gif')-(OLD.trash=0 AND OLD.kind='gif'),storage=storage+(CASE WHEN NEW.trash=0 THEN NEW.size ELSE 0 END)-(CASE WHEN OLD.trash=0 THEN OLD.size ELSE 0 END) WHERE account IN (SELECT account FROM account_photos WHERE photo=NEW.id);
        END;
        CREATE INDEX IF NOT EXISTS ix_photos_created ON photos(created);
        ''')
        if not self.query("SELECT 1 FROM settings WHERE key='accountMetricsVersion' AND value='1'"):
            self.db.execute('DELETE FROM account_media_stats')
            self.db.execute("INSERT INTO account_media_stats SELECT ap.account,SUM(p.trash=0),SUM(p.trash<>0),SUM(p.trash=0 AND p.kind='image'),SUM(p.trash=0 AND p.kind='video'),SUM(p.trash=0 AND p.kind='gif'),SUM(CASE WHEN p.trash=0 THEN p.size ELSE 0 END) FROM account_photos ap JOIN photos p ON p.id=ap.photo GROUP BY ap.account")
            self.db.execute("INSERT OR REPLACE INTO settings VALUES('accountMetricsVersion','1')");self.db.commit()
        if version<4:
            for account in self.query('SELECT id,categories FROM accounts'):
                self.sync_collections(account['id'],account['categories']);self.observe_identity(account['id'])
        if version<5:
            self.db.execute("UPDATE accounts SET last_published=COALESCE((SELECT MAX(published) FROM sources s WHERE s.account=accounts.id),''),last_success=COALESCE((SELECT MAX(updated) FROM tasks t WHERE t.account=accounts.id AND t.status='completed' AND t.mode IN ('latest','history') AND COALESCE(json_extract(t.options,'$.from'),'')='' AND COALESCE(json_extract(t.options,'$.to'),'')='' AND COALESCE(json_array_length(t.options,'$.kinds'),3)=3),'')")
        self.db.execute("UPDATE following_runs SET status='interrupted',message='上次读取中断，已读取账号保留，可继续' WHERE status='running'")
        self.db.commit()
        for column,definition in {'country':"TEXT DEFAULT ''",'suggested_country':"TEXT DEFAULT ''",'country_language':"TEXT DEFAULT ''",'language_checked':"TEXT DEFAULT ''",'pinned_avatar':"TEXT DEFAULT ''"}.items():
            if column not in {r[1] for r in self.db.execute('PRAGMA table_info(accounts)')}:self.db.execute('ALTER TABLE accounts ADD COLUMN '+column+' '+definition)
        if 'position' not in {r[1] for r in self.db.execute('PRAGMA table_info(account_collections)')}:self.db.execute('ALTER TABLE account_collections ADD COLUMN position INT DEFAULT 0')
        if version<6:self.db.execute("UPDATE accounts SET pinned_avatar=avatar_path WHERE avatar_path<>''")
        self.db.executescript('''CREATE TABLE IF NOT EXISTS note_presets(text TEXT PRIMARY KEY,uses INT,updated TEXT);
        CREATE TABLE IF NOT EXISTS similar_scan_items(photo TEXT PRIMARY KEY,algorithm TEXT,group_id TEXT,metadata TEXT,fingerprint TEXT,excluded INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS similar_ignored(signature TEXT PRIMARY KEY,created TEXT);
        CREATE INDEX IF NOT EXISTS ix_similar_groups ON similar_scan_items(group_id);
        CREATE INDEX IF NOT EXISTS ix_account_photos_photo ON account_photos(photo,account);
        ''')
        self.db.execute('PRAGMA user_version=6');self.db.commit()
        # Keep submitted queue entries across upgrades; only an interrupted running task pauses.
        self.write("UPDATE tasks SET status='paused',message='上次运行中断；已保存的图片保留，可继续' WHERE status='running'")
        if not self.query("SELECT 1 FROM settings WHERE key='queueRecoveryVersion' AND value='1'"):
            backups=sorted((self.root/'backups').glob('before-v3-*.db'),reverse=True)
            if backups:
                with closing(sqlite3.connect(backups[0].resolve().as_uri()+'?mode=ro',uri=True)) as previous:
                    previous.row_factory=sqlite3.Row
                    for old in previous.execute("SELECT id,created,updated FROM tasks WHERE status='queued'"):
                        self.db.execute("UPDATE tasks SET status='queued',message='已恢复升级前的待采集队列' WHERE id=? AND status='paused' AND message='上次运行中断；已保存的图片保留，可继续' AND created=? AND updated=?",(old['id'],old['created'],old['updated']))
            self.db.execute("INSERT OR REPLACE INTO settings VALUES('queueRecoveryVersion','1')");self.db.commit()
    def path(self,value):
        p=Path(value)
        if p.is_absolute():return p # legacy files remain readable until moved or repaired
        out=(self.root/p).resolve()
        if not out.is_relative_to(self.root):raise ValueError('无效资料库路径')
        return out
    def ensure_account(self,handle,profile=None):
        handle=str(handle).lstrip('@').strip()
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle):return ''
        profile=profile or {};uid=str(profile.get('id') or profile.get('id_str') or '');history_needed=False
        row=self.query('SELECT * FROM accounts WHERE handle=?',(handle,))
        stable=self.query('SELECT * FROM accounts WHERE external_id=? OR id=?',(uid,'x:'+uid)) if uid else []
        if stable:
            aid=stable[0]['id']
            if not row or row[0]['id']==aid:
                if stable[0]['handle']!=handle:self.observe_identity(aid);self.write('UPDATE accounts SET handle=? WHERE id=?',(handle,aid));self.mark_account_layout(aid);history_needed=True
        elif row:aid=row[0]['id']
        else:
            aid='x:'+uid if uid else 'handle:'+handle.lower()
            self.write('INSERT INTO accounts(id,handle,name,created) VALUES(?,?,?,?)',(aid,handle,str(profile.get('nick') or profile.get('name') or handle),now()))
            history_needed=True
        if profile:
            name=str(profile.get('nick') or profile.get('screen_name') or handle)
            avatar=str(profile.get('profile_image') or profile.get('profile_image_url_https') or profile.get('profile_image_url') or profile.get('avatar') or '')
            current=self.query('SELECT * FROM accounts WHERE id=?',(aid,))[0]
            if current['name']!=name or avatar and current['avatar_url']!=avatar:
                self.observe_identity(aid);self.write("UPDATE accounts SET name=?,avatar_url=CASE WHEN ?<>'' THEN ? ELSE avatar_url END WHERE id=?",(name,avatar,avatar,aid));self.observe_identity(aid)
                if avatar and avatar!=current['avatar_url'] and hasattr(self,'avatar_pool'):self.request_avatar(aid,avatar)
            if uid and current['external_id']!=uid:self.write('UPDATE accounts SET external_id=? WHERE id=?',(uid,aid))
            if 'protected' in profile:self.write('UPDATE accounts SET protected=? WHERE id=?',(int(bool(profile['protected'])),aid))
        if history_needed:self.observe_identity(aid)
        return aid
    def _source(self,photo,url,metadata,owner=''):
        post,key,author=media_info(metadata,url);handle=str(author.get('name') or handle_from_url(url))
        aid=self.ensure_account(handle,author) if handle else ''
        content=str(metadata.get('content') or metadata.get('full_text') or metadata.get('text') or '')
        published=str(metadata.get('date') or metadata.get('published') or '')
        if published and 'T' not in published:published=published.replace(' ','T')
        self.write('INSERT INTO sources(photo,url,metadata,account,post_id,published,content) VALUES(?,?,?,?,?,?,?) ON CONFLICT(photo,url) DO UPDATE SET metadata=excluded.metadata,account=excluded.account,post_id=excluded.post_id,published=excluded.published,content=excluded.content',(photo,url,json_text(metadata),aid,post,published,content))
        for account in {aid,owner}- {''}:
            self.write('INSERT OR IGNORE INTO account_photos VALUES(?,?,?)',(account,photo,now()))
            if published:self.write('UPDATE accounts SET last_published=MAX(last_published,?) WHERE id=?',(published,account))
            if metadata.get('lang') or metadata.get('language'):self.write("UPDATE accounts SET language_checked='' WHERE id=?",(account,))
        if key:self.write('INSERT OR REPLACE INTO media VALUES(?,?,?,?)',(key,photo,post,json_text(metadata)))
        self.mark_layout(photo)
        return key
    def record_item(self,task,key,photo,outcome,db=None):
        if not task:return
        connection=db or self.db
        connection.execute("INSERT INTO task_items VALUES(?,?,?,?,?) ON CONFLICT(task,media_key) DO UPDATE SET photo=excluded.photo,outcome=excluded.outcome WHERE task_items.outcome LIKE 'pending_%'",(task,key,photo,outcome,now()))
        connection.execute("UPDATE tasks SET imported=(SELECT COUNT(*) FROM task_items WHERE task=? AND outcome='new'),duplicates=(SELECT COUNT(*) FROM task_items WHERE task=? AND outcome='duplicate'),excluded=(SELECT COUNT(*) FROM task_items WHERE task=? AND outcome='excluded'),updated=? WHERE id=?",(task,task,task,now(),task))
    def ingest(self,paths,url='',metadata=None,task='',owner=''):
        totals=dict(added=0,duplicates=0,excluded=0,failed=0)
        for item in paths:
            p=Path(item)
            if p.suffix.lower() not in EXT:continue
            try:
                with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                key=media_info(metadata,url)[1] or 'local:'+digest
                with self.lock:
                    previous=self.query('SELECT outcome FROM task_items WHERE task=? AND media_key=?',(task,key)) if task else []
                    if previous and not previous[0]['outcome'].startswith('pending_'):
                        continue
                    blocked=bool(self.query('SELECT 1 FROM excluded_content WHERE photo=?',(digest,)) or self.query('SELECT 1 FROM excluded_media WHERE media_key=?',(key,)))
                    exists=self.query('SELECT * FROM photos WHERE id=?',(digest,))
                    if blocked:
                        if url and exists:self._source(digest,url,metadata or {},owner)
                        with self.transaction() as db:
                            db.execute('INSERT OR IGNORE INTO excluded_media VALUES(?,?,?)',(key,digest,now()));self.record_item(task,key,digest,'excluded',db)
                        totals['excluded']+=1;continue
                    missing=not exists or not self.path(exists[0]['path']).is_file()
                    planned_new=missing or bool(previous and previous[0]['outcome']=='pending_new')
                    if task and not previous:
                        self.write('INSERT OR IGNORE INTO task_items VALUES(?,?,?,?,?)',(task,key,digest,'pending_new' if missing else 'pending_duplicate',now()))
                    if missing:
                        im,kind,duration,(w,h)=inspect_media(p)
                        if (metadata or {}).get('type')=='animated_gif':kind='gif'
                        try:
                            thumb=im.convert('RGB');phash=visual_hash(im) if kind=='image' else '';thumb.thumbnail((640,640))
                            color='#%02x%02x%02x'%thumb.resize((1,1)).getpixel((0,0))
                            relative='originals/'+digest+p.suffix.lower();destination=self.root/relative
                            atomic_copy(p,destination)
                            temporary=self.root/'thumbs'/(digest+'.pending.jpg');thumb.save(temporary,quality=85);os.replace(temporary,self.root/'thumbs'/(digest+'.jpg'))
                        finally:im.close()
                        author=(metadata or {}).get('author') or {};author=author.get('name','') if isinstance(author,dict) else ''
                        with self.transaction() as db:
                            db.execute('INSERT INTO photos(id,path,width,height,size,created,tags,color,author,phash,kind,duration,analysis_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,width=excluded.width,height=excluded.height,size=excluded.size,trash=0,phash=excluded.phash,kind=excluded.kind,duration=excluded.duration',(digest,relative,w,h,destination.stat().st_size,now(),'竖图' if h>w*1.1 else '横图' if w>h*1.1 else '方图',color,author,phash,kind,duration,'pending' if kind=='image' else 'not_applicable'))
                            db.execute('UPDATE photos SET format=? WHERE id=?',(p.suffix.lower().lstrip('.'),digest))
                        outcome='new'
                    else:outcome='new' if planned_new else 'duplicate'
                    if url:self._source(digest,url,metadata or {},owner)
                    self.mark_layout(digest);self.organize_photo(digest)
                    with self.transaction() as db:self.record_item(task,key,digest,outcome,db)
                    totals['added' if outcome=='new' else 'duplicates']+=1
            except (OSError,ValueError,sqlite3.Error):totals['failed']+=1
        return totals
    def recover_task_counts(self):
        with self.transaction() as db:
            db.execute("UPDATE tasks SET imported=(SELECT COUNT(*) FROM task_items WHERE task=tasks.id AND outcome='new'),duplicates=(SELECT COUNT(*) FROM task_items WHERE task=tasks.id AND outcome='duplicate'),excluded=(SELECT COUNT(*) FROM task_items WHERE task=tasks.id AND outcome='excluded') WHERE mode<>'legacy'")
    def where(self,a):
        clauses=['p.trash=?'];args=[1 if a.get('view')=='trash' else 0]
        if a.get('view')=='favorite':clauses.append('p.favorite=1')
        if a.get('view')=='inbox':clauses.append('p.reviewed=0')
        if a.get('kind') in ['image','video','gif']:clauses.append('p.kind=?');args.append(a['kind'])
        if a.get('view')=='recent':clauses.append('p.created>=?');args.append((datetime.now(timezone.utc)-timedelta(days=7)).isoformat())
        for field,sql in [('account','EXISTS(SELECT 1 FROM account_photos ap WHERE ap.photo=p.id AND ap.account=?)'),('batch','EXISTS(SELECT 1 FROM task_items ti WHERE ti.photo=p.id AND ti.task=?)'),('album','EXISTS(SELECT 1 FROM album_photos al WHERE al.photo=p.id AND al.album=?)')]:
            if a.get(field):clauses.append(sql);args.append(a[field])
        account_filters=[];account_args=[]
        if a.get('account'):account_filters.append('ac.id=?');account_args.append(a['account'])
        if a.get('accountCategory'):
            account_filters.append("(','||ac.categories||',') LIKE ?");account_args.append('%,'+a['accountCategory']+',%')
        if a.get('accountRating') not in (None,'','all'):
            value=str(a['accountRating'])
            if value=='unrated':account_filters.append('ac.rating=0')
            elif value.endswith('+'):account_filters.append('ac.rating>=?');account_args.append(int(value[:-1]))
            else:account_filters.append('ac.rating=?');account_args.append(int(value))
        if account_filters:
            clauses.append('EXISTS(SELECT 1 FROM account_photos ar JOIN accounts ac ON ac.id=ar.account WHERE ar.photo=p.id AND '+' AND '.join(account_filters)+')');args.extend(account_args)
        if a.get('tag'):clauses.append("(','||REPLACE(p.tags,'，',',')||',') LIKE ?");args.append('%,'+a['tag']+',%')
        if a.get('shape')=='portrait':clauses.append('p.height>p.width')
        if a.get('shape')=='landscape':clauses.append('p.width>p.height')
        if a.get('shape')=='square':clauses.append('ABS(p.width-p.height)<MAX(p.width,p.height)*0.1')
        if a.get('minWidth'):clauses.append('p.width>=?');args.append(int(a['minWidth']))
        if a.get('textFilter')=='text':clauses.append('p.text_score>=?');args.append(float(a.get('textThreshold',.6)))
        if a.get('textFilter')=='pending':clauses.append("p.analysis_status='pending'")
        date='p.created' if a.get('dateField')!='published' else "(SELECT MAX(s.published) FROM sources s WHERE s.photo=p.id)"
        if a.get('from'):clauses.append(date+'>=?');args.append(a['from'])
        if a.get('to'):clauses.append(date+'<?');args.append(a['to']+'T23:59:59.999999+00:00')
        if a.get('q'):
            q='%'+str(a['q']).replace('!','!!').replace('%','!%').replace('_','!_')+'%'
            clauses.append("(p.tags LIKE ? ESCAPE '!' OR p.note LIKE ? ESCAPE '!' OR p.ocr_text LIKE ? ESCAPE '!' OR EXISTS(SELECT 1 FROM sources s LEFT JOIN accounts ac ON ac.id=s.account WHERE s.photo=p.id AND (s.content LIKE ? ESCAPE '!' OR ac.handle LIKE ? ESCAPE '!'))) ");args.extend([q]*5)
        if a.get('ids') is not None:
            ids=list(dict.fromkeys(a['ids']))
            if not ids:clauses.append('0')
            else:clauses.append('p.id IN ('+','.join('?' for _ in ids)+')');args.extend(ids)
        return ' AND '.join(clauses),args
    def list_photos(self,a):
        where,args=self.where(a);total=self.query('SELECT COUNT(*) n FROM photos p WHERE '+where,args)[0]['n']
        published="(SELECT MAX(s.published) FROM sources s WHERE s.photo=p.id)";prefix=[]
        if a.get('account'):published="COALESCE(NULLIF((SELECT MAX(s.published) FROM sources s WHERE s.photo=p.id AND s.account=?),''),"+published+")";prefix=[a['account']]
        order={'new':'p.created DESC,p.id','old':'p.created,p.id','size':'p.size DESC,p.id','published':"COALESCE(NULLIF(published,''),p.created) DESC,p.id DESC"}.get(a.get('sort'),'p.created DESC,p.id')
        limit=max(1,min(240,int(a.get('limit',60))));page=max(1,int(a.get('page',1)))
        rows=self.query("SELECT p.id,p.width,p.height,p.size,p.created,p.tags,p.favorite,p.trash,p.note,p.color,p.author,p.reviewed,p.text_score,p.analysis_status,p.parent,p.kind,p.duration,p.format,"+published+" published,(SELECT COUNT(*) FROM sources s WHERE s.photo=p.id) source_count FROM photos p WHERE "+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*prefix,*args,limit,(page-1)*limit))
        return dict(items=rows,total=total,page=page,pages=max(1,math.ceil(total/limit)),revision=self.revision)
    def select_ids(self,a):
        where,args=self.where(a);return [r['id'] for r in self.query('SELECT p.id FROM photos p WHERE '+where,args)]
    def detail(self,ident):
        rows=self.query('SELECT * FROM photos WHERE id=?',(ident,))
        if not rows:raise ValueError('图片不存在')
        row=rows[0];row.pop('path');row['sources']=self.query('SELECT s.url,s.content,s.published,s.post_id,s.account,ac.handle,ac.alias FROM sources s LEFT JOIN accounts ac ON ac.id=s.account WHERE s.photo=? ORDER BY s.published DESC',(ident,));row['albums']=self.query('SELECT a.* FROM albums a JOIN album_photos ap ON ap.album=a.id WHERE ap.photo=?',(ident,));return row
    def file_paths(self,ids):
        paths=[]
        for ident in ids:
            row=self.query('SELECT path FROM photos WHERE id=? AND trash<>2',(ident,))
            if row:
                p=self.path(row[0]['path'])
                if not p.is_file():
                    alternatives=[self.path(r['path']) for r in self.query('SELECT path FROM media_locations WHERE photo=?',(ident,))];p=next((f for f in alternatives if f.is_file()),p)
                    if p.is_file():self.mark_layout(ident)
                if p.is_file():paths.append(str(p))
        return paths
    def image(self,ident,full=False):
        rows=self.query('SELECT path,kind FROM photos WHERE id=?',(ident,))
        if not rows:raise ValueError('图片不存在')
        if full and rows[0]['kind']=='image':
            with Image.open(self.path(rows[0]['path'])) as im:
                im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((2400,2400));stream=io.BytesIO();im.save(stream,format='JPEG',quality=92);data=stream.getvalue()
        else:
            p=self.root/'thumbs'/(ident+'.jpg')
            if not p.exists():
                im,_,_,_=inspect_media(self.path(rows[0]['path']))
                try:im.thumbnail((640,640));im.save(p,quality=85)
                finally:im.close()
            data=p.read_bytes()
        return 'data:image/jpeg;base64,'+base64.b64encode(data).decode()
    def edit(self,a):
        ids=list(dict.fromkeys(a.get('ids',[])));before=[]
        with self.transaction() as db:
            for ident in ids:
                row=db.execute('SELECT id,tags,favorite,trash,note,reviewed FROM photos WHERE id=?',(ident,)).fetchone()
                if not row:continue
                row=dict(row);before.append(row)
                changes={k:a[k] for k in ['favorite','trash','note','reviewed'] if k in a}
                if 'tags' in a:
                    old=tags(row['tags']);new=tags(a['tags']);mode=a.get('tagMode','replace')
                    changes['tags']=','.join(list(dict.fromkeys(old+new)) if mode=='add' else [t for t in old if t not in new] if mode=='remove' else new)
                if changes:
                    db.execute('UPDATE photos SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),ident))
                if a.get('trash')==1:
                    db.execute('INSERT OR IGNORE INTO excluded_content VALUES(?,?)',(ident,now()))
                    db.execute('INSERT OR IGNORE INTO excluded_media SELECT media_key,photo,? FROM media WHERE photo=?',(now(),ident))
                elif a.get('trash')==0:
                    db.execute('DELETE FROM excluded_content WHERE photo=?',(ident,));db.execute('DELETE FROM excluded_media WHERE photo=?',(ident,))
            if before:db.execute('INSERT INTO undo VALUES(?,?,?)',(uuid.uuid4().hex,now(),json_text(before)))
            db.execute('DELETE FROM undo WHERE id NOT IN (SELECT id FROM undo ORDER BY created DESC LIMIT 30)')
        if 'trash' in a:
            for ident in ids:self.mark_layout(ident)
            self.reconcile_layout(limit=len(ids))
        return dict(updated=len(before))
    def undo(self):
        rows=self.query('SELECT * FROM undo ORDER BY created DESC LIMIT 1')
        if not rows:raise ValueError('没有可撤销的操作')
        payload=json.loads(rows[0]['payload'])
        if isinstance(payload,dict):
            if payload.get('kind')=='accounts':
                for row in payload['items']:
                    if self.query('SELECT 1 FROM accounts WHERE id=?',(row['id'],)):self.save_account(row)
            elif payload.get('kind')=='album':
                with self.transaction() as db:
                    for ident in payload['ids']:
                        db.execute('DELETE FROM album_photos WHERE album=? AND photo=?',(payload['album'],ident))
                    for ident in payload['members']:db.execute('INSERT OR IGNORE INTO album_photos VALUES(?,?)',(payload['album'],ident))
            elif payload.get('kind')=='removedAccount':self.restore_removed_account(payload)
            else:raise ValueError('未知撤销记录，未更改资料库')
            self.write('DELETE FROM undo WHERE id=?',(rows[0]['id'],));return True
        with self.transaction() as db:
            for row in json.loads(rows[0]['payload']):
                current=db.execute('SELECT trash FROM photos WHERE id=?',(row['id'],)).fetchone()
                if current and current['trash']==2:continue
                db.execute('UPDATE photos SET tags=?,favorite=?,trash=?,note=?,reviewed=? WHERE id=?',(row['tags'],row['favorite'],row['trash'],row['note'],row['reviewed'],row['id']))
                if row['trash']==0:db.execute('DELETE FROM excluded_content WHERE photo=?',(row['id'],));db.execute('DELETE FROM excluded_media WHERE photo=?',(row['id'],))
                else:db.execute('INSERT OR IGNORE INTO excluded_content VALUES(?,?)',(row['id'],now()))
            db.execute('DELETE FROM undo WHERE id=?',(rows[0]['id'],))
        for row in json.loads(rows[0]['payload']):self.mark_layout(row['id'])
        self.reconcile_layout(limit=None)
        return True
    def purge(self,ids):
        count=0
        for ident in ids:
            rows=self.query('SELECT path FROM photos WHERE id=? AND trash=1',(ident,))
            if not rows:continue
            locations=[self.path(r['path']) for r in self.query('SELECT path FROM media_locations WHERE photo=?',(ident,))]+[self.path(rows[0]['path'])]
            for file in set(locations):
                file.unlink(missing_ok=True);self._remove_empty_parents(file)
            self.write('DELETE FROM media_locations WHERE photo=?',(ident,));self.write('DELETE FROM layout_jobs WHERE photo=?',(ident,));(self.root/'thumbs'/(ident+'.jpg')).unlink(missing_ok=True)
            self.write("UPDATE photos SET trash=2,path='' WHERE id=?",(ident,));self.write('DELETE FROM embeddings WHERE photo=?',(ident,));count+=1
        return count
    def accounts(self,a=None):
        a=a or {};q='%'+str(a.get('q',''))+'%';page=max(1,int(a.get('page',1)));size=24
        clauses=['(ac.handle LIKE ? OR ac.alias LIKE ?)'];args=[q,q]
        if a.get('category'):clauses.append("(','||ac.categories||',') LIKE ?");args.append('%,'+a['category']+',%')
        if a.get('rating') not in (None,'','all'):
            rating=str(a['rating'])
            if rating=='unrated':clauses.append('ac.rating=0')
            elif rating.endswith('+'):clauses.append('ac.rating>=?');args.append(int(rating[:-1]))
            else:clauses.append('ac.rating=?');args.append(int(rating))
        where=' AND '.join(clauses);order='ac.rating DESC,ac.created DESC' if a.get('sort')=='rating' else 'ac.created DESC'
        total=self.query('SELECT COUNT(*) n FROM accounts ac WHERE '+where,args)[0]['n']
        items=self.query('''SELECT ac.*,(SELECT COUNT(*) FROM account_photos ap JOIN photos p ON p.id=ap.photo WHERE ap.account=ac.id AND p.trash=0) retained,(SELECT COUNT(*) FROM account_photos ap JOIN photos p ON p.id=ap.photo WHERE ap.account=ac.id AND p.trash<>0) deleted,(SELECT COUNT(*) FROM tasks t WHERE t.account=ac.id) batches FROM accounts ac WHERE '''+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*args,size,(page-1)*size))
        return dict(items=items,total=total,pages=max(1,math.ceil(total/size)),page=page)
    def account_detail(self,ident):
        rows=self.query('SELECT * FROM accounts WHERE id=?',(ident,))
        if not rows:raise ValueError('账号不存在')
        row=rows[0];row['tasks']=self.query('SELECT * FROM tasks WHERE account=? ORDER BY created DESC LIMIT 50',(ident,));row['retained']=self.query('SELECT COUNT(*) n FROM account_photos ap JOIN photos p ON p.id=ap.photo WHERE ap.account=? AND p.trash=0',(ident,))[0]['n'];return row
    def save_account(self,a):
        allowed={k:str(a[k]) for k in ['alias','note','avatar_url','custom_avatar','avatar_path','avatar_fetched_url','country','pinned_avatar'] if k in a}
        if 'country' in allowed:
            allowed['country']=allowed['country'].upper()
            if allowed['country'] not in ('','--') and not re.fullmatch('[A-Z]{2}',allowed['country']):raise ValueError('请选择有效的国家或地区')
        if a.get('note'):self.remember_note(a['note'])
        if any(k in a for k in ['avatar_url','custom_avatar','avatar_path']):self.observe_identity(a['id'])
        if 'rating' in a:
            rating=int(a['rating'])
            if not 0<=rating<=5:raise ValueError('账号评分范围为 1–5 星，0 表示未评分')
            allowed['rating']=rating
        if 'categories' in a:allowed['categories']=','.join(tags(a['categories']))
        old_categories=self.query('SELECT categories FROM accounts WHERE id=?',(a['id'],)) if 'categories' in a else []
        if old_categories and len(tags(allowed['categories']))>max(3,len(tags(old_categories[0]['categories']))):raise ValueError('一个账号最多选择 3 个合集')
        if allowed:self.write('UPDATE accounts SET '+','.join(k+'=?' for k in allowed)+' WHERE id=?',(*allowed.values(),a['id']))
        if old_categories and old_categories[0]['categories']!=allowed['categories']:self.sync_collections(a['id'],allowed['categories']);self.mark_account_layout(a['id'])
        if any(k in a for k in ['avatar_url','custom_avatar','avatar_path']):self.observe_identity(a['id'])
        return True
    def album(self,a):
        action=a.get('action','create')
        if action=='create':
            name=str(a['name']).strip()
            if not name:raise ValueError('请输入相册名称')
            ident=uuid.uuid4().hex;self.write('INSERT INTO albums VALUES(?,?,?)',(ident,name,now()));return ident
        if action in ['add','remove']:
            with self.transaction() as db:
                members=[ident for ident in a['ids'] if db.execute('SELECT 1 FROM album_photos WHERE album=? AND photo=?',(a['album'],ident)).fetchone()]
                db.execute('INSERT INTO undo VALUES(?,?,?)',(uuid.uuid4().hex,now(),json_text(dict(kind='album',album=a['album'],ids=list(dict.fromkeys(a['ids'])),members=members))))
                for ident in a['ids']:
                    if action=='add':db.execute('INSERT OR IGNORE INTO album_photos VALUES(?,?)',(a['album'],ident))
                    else:db.execute('DELETE FROM album_photos WHERE album=? AND photo=?',(a['album'],ident))
            return True
        raise ValueError('无效相册操作')
    def settings(self):return {r['key']:json.loads(r['value']) for r in self.query('SELECT * FROM settings')}
    def save_settings(self,a):
        for key,value in a.items():self.write('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json_text(value)))
        return self.settings()
    def stats(self):
        counts={r['trash']:r['n'] for r in self.query('SELECT trash,COUNT(*) n FROM photos GROUP BY trash')}
        alltags=[]
        for row in self.query('SELECT DISTINCT tags FROM photos WHERE trash=0'):alltags.extend(tags(row['tags']))
        categories=sorted({t for row in self.query('SELECT DISTINCT categories FROM accounts') for t in tags(row['categories'])})
        return dict(root=str(self.root),total=counts.get(0,0),trash=counts.get(1,0),revision=self.revision,tags=sorted(set(alltags)),accountCategories=categories,albums=self.query('SELECT a.*,(SELECT COUNT(*) FROM album_photos ap JOIN photos p ON p.id=ap.photo WHERE ap.album=a.id AND p.trash=0) count FROM albums a ORDER BY a.created'),pending=self.query("SELECT COUNT(*) n FROM photos WHERE trash=0 AND analysis_status='pending'")[0]['n'],bytes=self.query('SELECT COALESCE(SUM(size),0) n FROM photos WHERE trash<>2')[0]['n'])
    def similar(self,threshold=6):
        rows=self.query("SELECT id,phash,color,width,height,size FROM photos WHERE trash=0 AND kind='image' AND phash<>''");buckets={};parent={r['id']:r['id'] for r in rows};lookup={r['id']:r for r in rows}
        def find(x):
            while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
            return x
        for row in rows:
            value=int(row['phash'],16);candidates=set()
            for band in range(4):candidates.update(buckets.get((band,(value>>(band*16))&65535),[]))
            for other in candidates:
                r=lookup[other];v=int(r['phash'],16)
                if (v^value).bit_count()<=threshold and abs(row['width']/row['height']-r['width']/r['height'])<.25:
                    parent[find(row['id'])]=find(other)
            for band in range(4):buckets.setdefault((band,(value>>(band*16))&65535),[]).append(row['id'])
        groups={}
        for row in rows:groups.setdefault(find(row['id']),[]).append(row['id'])
        return [g for g in groups.values() if len(g)>1]
    def export(self,a):
        out=Path(a['path'])/('Luma-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:4]);out.mkdir();records=[]
        for ident in a['ids']:
            rows=self.query('SELECT path FROM photos WHERE id=?',(ident,))
            if not rows:continue
            p=self.path(rows[0]['path'])
            if p.is_file():shutil.copy2(p,out/p.name);records.append(self.detail(ident))
        (out/'metadata.json').write_text(json_text(records),encoding='utf-8');return dict(count=len(records),path=str(out))
    def check(self):
        missing=[p['id'] for p in self.query('SELECT id,path FROM photos WHERE trash<>2') if not self.path(p['path']).is_file()]
        return dict(database=self.query('PRAGMA quick_check')[0],missing=missing,exclusions=self.query('SELECT COUNT(*) n FROM excluded_content')[0]['n'])
    def snapshot(self,target):
        with self.lock:return self._snapshot(target)
    def _snapshot(self,target):
        target=Path(target).resolve()
        if target==self.root or target.is_relative_to(self.root):raise ValueError('备份或迁移目标不能放在资料库内部')
        target.mkdir(parents=True,exist_ok=True)
        if (target/'library.db').exists():raise ValueError('目标已包含资料库，请选择新的空文件夹')
        folders=['originals','avatars','thumbs','models','edits','staging','backups']
        primaries={str(self.path(r['path'])).casefold() for r in self.query('SELECT path FROM photos WHERE trash<>2')}
        aliases={str(self.path(r['path'])).casefold() for r in self.query('SELECT path FROM media_locations')}-primaries
        files=[p for folder in folders for p in (self.root/folder).rglob('*') if p.is_file() and not (folder=='models' and p.name.endswith('.part'))]
        files.sort(key=lambda p:(str(p).casefold() not in primaries,str(p)))
        def file_key(p):
            stat=p.stat();return (stat.st_dev,stat.st_ino) if stat.st_ino else str(p)
        sizes={file_key(p):p.stat().st_size for p in files};total=sum(sizes.values())+(self.root/'library.db').stat().st_size
        if shutil.disk_usage(target).free<total+100*1024*1024:raise ValueError('目标空间不足')
        skipped_aliases=0
        with self.lock:
            copied={}
            for p in files:
                out=target/p.relative_to(self.root);out.parent.mkdir(parents=True,exist_ok=True);key=file_key(p)
                if key in copied:
                    try:os.link(copied[key],out);continue
                    except OSError:
                        if str(p).casefold() in aliases:skipped_aliases+=1;continue
                atomic_copy(p,out)
                with p.open('rb') as src,out.open('rb') as dst:
                    if hashlib.file_digest(src,'sha256').digest()!=hashlib.file_digest(dst,'sha256').digest():raise OSError('复制校验失败，原资料库未改变')
                copied[key]=out
            with closing(sqlite3.connect(target/'library.db')) as out:self.db.backup(out)
            with closing(sqlite3.connect(target/'library.db')) as out:
                if out.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise OSError('目标数据库校验失败')
        (target/'luma-library.json').write_text(json_text({'version':5,'storageLayout':1,'created':now()}),encoding='utf-8')
        return dict(path=str(target),bytes=total,skippedAliases=skipped_aliases)
