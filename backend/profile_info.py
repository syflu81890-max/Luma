"""Read-only startup discovery; never initializes Store or changes task states."""
import json,sqlite3,os,shutil,hashlib
from pathlib import Path
from contextlib import closing

def identity(path):
    try:
        stat=Path(path).stat();return f'{stat.st_dev}:{stat.st_ino}'
    except OSError:return ''

def inspect_profile(profile):
    profile=Path(profile);config=profile/'library-location.json'
    result=dict(profile=str(profile),configured=config.is_file(),photos=0,tasks=0,statuses={},configIdentity=identity(config),databaseIdentity='',libraryPath=str(profile/'library'),exists=profile.is_dir(),error='')
    try:
        if config.is_file():
            configured=Path(json.loads(config.read_text(encoding='utf-8-sig'))['path'])
            logical=Path.home()/'AppData'/'Roaming'/profile.name/'library'
            if str(configured).casefold()==str(logical).casefold() and '/localcache/roaming/' in profile.as_posix().casefold() and (profile/'library/library.db').is_file():configured=profile/'library'
            result['libraryPath']=str(configured)
        dbfile=Path(result['libraryPath'])/'library.db';result['databaseIdentity']=identity(dbfile);result['databaseExists']=dbfile.is_file()
        if dbfile.is_file():
            with closing(sqlite3.connect(dbfile.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
                db.execute('PRAGMA query_only=ON');tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'photos' in tables:result['photos']=db.execute('SELECT COUNT(*) FROM photos').fetchone()[0]
                if 'tasks' in tables:
                    result['tasks']=db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0];result['statuses']=dict(db.execute('SELECT status,COUNT(*) FROM tasks GROUP BY status'))
        result['sessionAvailable']=(profile/'Local State').is_file() and (profile/'Partitions').is_dir()
    except Exception as exc:result['error']=str(exc)
    return result

def snapshot_library(source,target):
    """Preserve a legacy in-profile library outside virtualized AppData, without editing it."""
    source=Path(source).resolve();target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):raise ValueError('配置迁移的资料库目标非空，已停止')
    target.mkdir(parents=True,exist_ok=True)
    if target==source or target.is_relative_to(source):raise ValueError('资料库目标不能位于原库内')
    for src in source.rglob('*'):
        if not src.is_file() or src.parent==source and src.name in ('library.db','library.db-wal','library.db-shm'):continue
        dst=target/src.relative_to(source);dst.parent.mkdir(parents=True,exist_ok=True)
        if src.is_relative_to(source/'originals'):
            try:os.link(src,dst);continue
            except OSError:pass
        shutil.copy2(src,dst)
        with src.open('rb') as a,dst.open('rb') as b:
            if hashlib.file_digest(a,'sha256').digest()!=hashlib.file_digest(b,'sha256').digest():raise OSError('旧库复制校验失败，原库保留')
    with closing(sqlite3.connect((source/'library.db').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target/'library.db')) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise OSError('资料库快照校验失败')
    return dict(path=str(target))
