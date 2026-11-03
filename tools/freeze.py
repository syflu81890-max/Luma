"""Freeze independent executables; never import gallery-dl into the core bundle."""
import ast,json,os,subprocess,sys
from pathlib import Path
import importlib.metadata as metadata

root=Path(__file__).resolve().parents[1]

def run(*args):
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir',*args],cwd=root,check=True)

def main():
    run('--name','luma-backend','--collect-all','rapidocr_onnxruntime','--collect-all','onnxruntime','--collect-all','tokenizers',
        '--copy-metadata','Pillow','--exclude-module','gallery_dl','--exclude-module','imageio_ffmpeg','--distpath','backend-dist','backend/app.py')
    # Image processing uses cv2, not its optional external video plugin. Media
    # previews use the independent FFmpeg executable built from known source.
    base=(root/'backend-dist/luma-backend').resolve()
    for path in base.rglob('opencv_videoio_ffmpeg*.dll'):
        assert path.resolve().is_relative_to(base)
        path.unlink()
    hidden={'xml.etree.ElementTree','html.parser','http.cookiejar','email.mime.text','ctypes','sqlite3','netrc','gzip','bz2','lzma','configparser','getpass','mimetypes','asyncio','multiprocessing'}
    # Upstream wheels are installed at runtime. Include the stdlib modules they
    # use, while excluding every optional external distribution from the EXE.
    for name in ('gallery-dl','requests','urllib3','charset-normalizer','idna','certifi'):
        dist=metadata.distribution(name)
        for file in dist.files or []:
            if str(file).endswith('.py'):
                try:tree=ast.parse(dist.locate_file(file).read_text(encoding='utf-8-sig'))
                except (OSError,SyntaxError,UnicodeError):continue
                for node in ast.walk(tree):
                    values=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and not node.level else []
                    for value in values:
                        if value and value.split('.')[0] in sys.stdlib_module_names and value.split('.')[0] not in {'posix','pwd','grp','fcntl','termios','readline','resource','syslog','nis','_posixsubprocess'}:hidden.add(value)
    args=['--name','luma-collector','--distpath','collector-dist','--add-data',f'collector/engine-lock.json{os.pathsep}.']
    for module in sorted(hidden):args+=['--hidden-import',module]
    for module in ('gallery_dl','requests','urllib3','charset_normalizer','idna','certifi','PIL','numpy','cv2','onnxruntime','tokenizers','rapidocr_onnxruntime','shapely','imageio_ffmpeg','huggingface_hub'):
        args+=['--exclude-module',module]
    run(*args,'collector/app.py')
    report={}
    for name,folder in [('core',root/'backend-dist/luma-backend'),('collector',root/'collector-dist/luma-collector')]:
        files=[p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()]
        forbidden=['gallery_dl','imageio_ffmpeg','opencv_videoio_ffmpeg'] if name=='core' else ['gallery_dl','requests','onnxruntime','rapidocr','tokenizers','numpy','cv2','shapely']
        found=[f for f in files if any(q in f.lower() for q in forbidden)]
        if found:raise RuntimeError(f'Unexpected bundled module in {name}: {found}')
        report[name]=dict(fileCount=len(files),bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()),excluded=forbidden)
    (root/'output').mkdir(exist_ok=True)
    (root/'output/freeze-public.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
