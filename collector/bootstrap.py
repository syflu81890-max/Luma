# SPDX-License-Identifier: GPL-2.0-only
"""Fetch optional engine wheels directly from upstream on the end user's PC.

The public collector EXE contains no gallery-dl/requests distribution. Versions
and hashes are fixed at release time. Wheel members are data until verified and
placed in a complete cache; no pip, shell commands, setup.py or .pth execution.
"""
import hashlib,json,os,shutil,sys,tempfile,time,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse
from urllib.request import HTTPSHandler,ProxyHandler,build_opener

def lock_data():
    source=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'engine-lock.json'
    return json.loads(source.read_text(encoding='utf-8'))

def cache_root():
    explicit=os.environ.get('LUMA_ENGINE_CACHE')
    if explicit:return Path(explicit).resolve()
    isolated=os.environ.get('LUMA_TEST_ROOT')
    if isolated:return Path(isolated).resolve()/'components'
    return Path.home()/'.luma-desktop/Components'

def valid_cache(folder,manifest):
    try:
        stored=json.loads((folder/'installed.json').read_text(encoding='utf-8'))
        if stored.get('manifest')!=manifest or not stored.get('files'):return False
        for relative,digest in stored['files'].items():
            path=(folder/relative).resolve()
            if not path.is_relative_to(folder.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:return False
        return True
    except (OSError,ValueError,TypeError):return False

def install_engine(manifest,base,proxy='',progress=lambda text:None):
    identity=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
    folder=base/('engine-'+identity)
    if valid_cache(folder,manifest):return folder
    base.mkdir(parents=True,exist_ok=True)
    marker=base/('engine-'+identity+'.lock');deadline=time.monotonic()+240
    while True:
        try:
            handle=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(handle);break
        except FileExistsError:
            if valid_cache(folder,manifest):return folder
            try:
                if time.time()-marker.stat().st_mtime>300:marker.unlink();continue
            except FileNotFoundError:continue
            if time.monotonic()>deadline:raise RuntimeError('采集组件准备仍未结束，请稍后重试')
            time.sleep(.2)
    try:
        if valid_cache(folder,manifest):return folder
        handlers=[HTTPSHandler()]
        if proxy:handlers.append(ProxyHandler({'https':proxy,'http':proxy}))
        opener=build_opener(*handlers)
        with tempfile.TemporaryDirectory(prefix='luma-engine-',dir=base) as temporary:
            staging=Path(temporary)/'ready';staging.mkdir();files={}
            for package in manifest['packages']:
                url=package['url'];parsed=urlparse(url)
                if parsed.scheme!='https' or parsed.hostname!='files.pythonhosted.org' or parsed.username or parsed.password:raise ValueError('组件下载地址不受信任')
                progress('首次准备采集组件：'+package['name']+' '+package['version'])
                with opener.open(url,timeout=35) as response:
                    body=response.read(int(package['size'])+1)
                if len(body)!=package['size'] or hashlib.sha256(body).hexdigest()!=package['sha256']:raise ValueError('组件校验失败，请重试；未运行下载内容')
                archive=Path(temporary)/package['filename'];archive.write_bytes(body)
                with zipfile.ZipFile(archive) as wheel:
                    if sum(i.file_size for i in wheel.infolist())>80*1024*1024:raise ValueError('组件展开大小异常')
                    for entry in wheel.infolist():
                        relative=PurePosixPath(entry.filename)
                        if entry.is_dir():continue
                        target=(staging/str(relative)).resolve()
                        if relative.is_absolute() or '\\' in entry.filename or not target.is_relative_to(staging.resolve()) or (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('组件包含非法路径')
                        if target.exists():raise ValueError('组件文件重叠')
                        data=wheel.read(entry);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);files[relative.as_posix()]=hashlib.sha256(data).hexdigest()
                marker.touch()
            (staging/'installed.json').write_text(json.dumps(dict(manifest=manifest,files=files),ensure_ascii=False),encoding='utf-8')
            if folder.exists():
                # Preserve a corrupted cache for diagnosis; no recursive deletion.
                folder.rename(base/(folder.name+'-invalid-'+str(time.time_ns())))
            staging.rename(folder)
        return folder
    finally:marker.unlink(missing_ok=True)

def ensure_engine(proxy='',progress=lambda text:None):
    if not getattr(sys,'frozen',False):return
    location=install_engine(lock_data(),cache_root(),proxy,progress)
    sys.path.insert(0,str(location))
