"""Real account/category/type folders with journaled, deduplicated hard links."""
import hashlib,os,re,sqlite3
from pathlib import Path

def folder_name(value,fallback='未分类'):
    text=str(value).strip();safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',text).strip(' .')[:36].rstrip(' .')
    reserved=safe.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
    if not safe:return fallback+'-'+hashlib.sha256(text.encode()).hexdigest()[:6] if text else fallback
    if safe!=text or reserved:safe+='-'+hashlib.sha256(text.encode()).hexdigest()[:6]
    return safe

class StorageLayout:
    def mark_layout(self,photo):
        self.write("INSERT INTO layout_jobs(photo) VALUES(?) ON CONFLICT(photo) DO UPDATE SET error=''",(photo,))
    def mark_account_layout(self,account):
        self.write("INSERT INTO layout_jobs(photo) SELECT photo FROM account_photos WHERE account=? ON CONFLICT(photo) DO UPDATE SET error=''",(account,))
    def storage_status(self):
        return dict(version=1,pattern='originals / @账号 / 分类 / 照片·视频·GIF',pending=self.query('SELECT COUNT(*) n FROM layout_jobs')[0]['n'],errors=self.query("SELECT photo,error FROM layout_jobs WHERE error<>'' LIMIT 5"),aliasWarnings=getattr(self,'layout_alias_warnings',0))
    def _remove_empty_parents(self,path):
        stop=self.root/'originals';parent=path.parent
        while parent!=stop and parent.is_relative_to(stop):
            try:parent.rmdir()
            except OSError:break
            parent=parent.parent
    def organize_photo(self,ident):
        from store import atomic_copy,tags
        with self.lock:
            rows=self.query('SELECT * FROM photos WHERE id=?',(ident,))
            if not rows or rows[0]['trash']==2:self.write('DELETE FROM layout_jobs WHERE photo=?',(ident,));return False
            row=rows[0];source=self.path(row['path'])
            old=[self.path(r['path']) for r in self.query('SELECT path FROM media_locations WHERE photo=?',(ident,))]
            if not source.is_file():
                source=next((p for p in old if p.is_file()),source)
            if not source.is_file():
                # A pre-layout database backup can be restored against the reorganized files.
                index=getattr(self,'_layout_file_index',None)
                if index is None:
                    index={}
                    for p in (self.root/'originals').rglob('*'):
                        if p.is_file():index.setdefault(p.stem,[]).append(p)
                    self._layout_file_index=index
                for candidate in index.get(ident,[]):
                    if not candidate.is_file():continue
                    if re.fullmatch('[a-f0-9]{64}',ident):
                        with candidate.open('rb') as f:
                            if hashlib.file_digest(f,'sha256').hexdigest()!=ident:continue
                    source=candidate;break
            if not source.is_file():raise OSError('原文件缺失，未改变资料库路径')
            accounts=self.query('SELECT ac.* FROM account_photos ap JOIN accounts ac ON ac.id=ap.account WHERE ap.photo=? ORDER BY ap.first_seen,ac.id',(ident,))
            base=Path('originals')/('_回收站' if row['trash'] else '')
            kind={'image':'照片','video':'视频','gif':'GIF'}.get(row['kind'],'照片')
            extension='.'+str(row['format'] or source.suffix.lstrip('.')).lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,8}',extension):raise ValueError('媒体扩展名无效')
            desired=[]
            for account in accounts or [dict(handle='_本地导入',categories='')]:
                name='@'+account['handle'] if account['handle']!='_本地导入' else '_本地导入'
                for category in tags(account['categories']) or ['未分类']:
                    relative=base/folder_name(name)/folder_name(category)/kind/(ident+extension)
                    if relative.as_posix().casefold() not in {p.as_posix().casefold() for p in desired}:desired.append(relative)
            primary=desired[0];destination=self.root/primary;destination.parent.mkdir(parents=True,exist_ok=True)
            reference=source
            def verified(p):
                if os.path.samefile(reference,p):return True
                with reference.open('rb') as src,p.open('rb') as dst:return hashlib.file_digest(src,'sha256').digest()==hashlib.file_digest(dst,'sha256').digest()
            if destination.exists():
                if not destination.is_file() or not verified(destination):raise OSError('目标存在内容不同的文件，已保留原文件并停止整理')
            else:
                try:os.link(source,destination)
                except OSError:atomic_copy(source,destination)
                if not verified(destination):raise OSError('目录迁移校验失败，原文件保留')
            reference=destination
            available=[primary]
            for relative in desired[1:]:
                target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():
                    if not target.is_file() or not verified(target):raise OSError('分类目录存在不同内容，未覆盖文件')
                else:
                    try:os.link(destination,target)
                    except OSError:
                        self.layout_alias_warnings=getattr(self,'layout_alias_warnings',0)+1
                        continue # Never duplicate the media just to populate another category.
                available.append(relative)
            with self.transaction() as db:
                db.execute('UPDATE photos SET path=?,format=? WHERE id=?',(primary.as_posix(),extension[1:],ident))
                db.execute('DELETE FROM media_locations WHERE photo=?',(ident,))
                db.executemany('INSERT INTO media_locations(photo,path) VALUES(?,?)',[(ident,p.as_posix()) for p in available])
                db.execute('DELETE FROM layout_jobs WHERE photo=?',(ident,))
            keep={str(self.root/p).casefold() for p in available}
            for p in set(old+[self.path(row['path'])]):
                if str(p).casefold() in keep or not p.is_relative_to(self.root/'originals'):continue
                try:
                    if p.is_file() and verified(p):p.unlink();self._remove_empty_parents(p)
                except OSError:
                    # Retain old locations in the journal until an open player releases them.
                    self.write('INSERT OR IGNORE INTO media_locations(photo,path) VALUES(?,?)',(ident,p.relative_to(self.root).as_posix()));self.mark_layout(ident)
            return True
    def reconcile_layout(self,limit=20,retry=False):
        if retry:self.write("UPDATE layout_jobs SET error=''")
        sql="SELECT photo FROM layout_jobs WHERE error='' ORDER BY photo";args=()
        if limit is not None:sql+=' LIMIT ?';args=(limit,)
        moved=0
        for job in self.query(sql,args):
            if getattr(self,'closed',False) or getattr(self,'maintenance',False):break
            try:moved+=int(self.organize_photo(job['photo']))
            except (OSError,ValueError,sqlite3.Error) as exc:self.write('UPDATE layout_jobs SET error=? WHERE photo=?',(str(exc)[:300],job['photo']))
        return dict(organized=moved,**self.storage_status())
