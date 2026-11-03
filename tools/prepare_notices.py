"""Collect original license/NOTICE files and pinned source provenance."""
import hashlib,importlib.metadata as metadata,json,platform,re,shutil,sys,urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[1]

def download(url,target,expected=None):
    target.parent.mkdir(parents=True,exist_ok=True)
    data=target.read_bytes() if target.exists() else urllib.request.urlopen(url,timeout=90).read()
    digest=hashlib.sha256(data).hexdigest()
    if expected and digest!=expected:raise ValueError('Source hash mismatch: '+target.name)
    if not target.exists():target.write_bytes(data)
    return dict(file=target.name,url=url,sha256=digest,bytes=len(data))

def main():
    dest=root/'licenses';dest.mkdir(exist_ok=True);inventory=[]
    for dist in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
        name=dist.metadata['Name'];version=dist.version;folder=dest/'python'/f'{name}-{version}';copied=[]
        for file in dist.files or []:
            source=dist.locate_file(file)
            if source.is_file() and re.search(r'(?i)(license|copying|notice|authors)',Path(file).name):
                relative=Path(*[s for s in Path(file).parts if s not in ('..','.','/')]);target=folder/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);copied.append(relative.as_posix())
        record=dict(name=name,version=version,license=dist.metadata.get('License-Expression') or dist.metadata.get('License') or '',licenses=copied,scope='build environment; only used modules are packaged')
        if name.lower().replace('_','-') in ('gallery-dl','imageio-ffmpeg'):record['scope']='development only; excluded from public executables'
        inventory.append(record)
    # These wheels omit a standalone license text; retain upstream texts too.
    for path,url in {
        'python/RapidOCR-Apache-2.0.txt':'https://raw.githubusercontent.com/RapidAI/RapidOCR/main/LICENSE',
        'python/tokenizers-Apache-2.0.txt':'https://raw.githubusercontent.com/huggingface/tokenizers/main/LICENSE',
        'Python-LICENSE.txt':'https://raw.githubusercontent.com/python/cpython/v'+platform.python_version()+'/LICENSE'
    }.items():download(url,dest/path)
    lock=json.loads((root/'package-lock.json').read_text(encoding='utf-8'))
    for name in ('electron','react','react-dom','scheduler','lucide-react','flag-icons'):
        package=root/'node_modules'/name;folder=dest/'node'/name;folder.mkdir(parents=True,exist_ok=True)
        found=[]
        for source in package.iterdir():
            if source.is_file() and re.search(r'(?i)(license|copying|notice)',source.name):shutil.copyfile(source,folder/source.name);found.append(source.name)
        info=json.loads((package/'package.json').read_text(encoding='utf-8'));inventory.append(dict(name=name,version=info['version'],license=info.get('license'),licenses=found,scope='runtime'))
    electron=root/'node_modules/electron/dist'
    for name in ('LICENSE','LICENSES.chromium.html'):
        source=electron/name
        if source.is_file():shutil.copyfile(source,dest/('Electron-'+name))
    sources=root/'third-party-sources';sources.mkdir(exist_ok=True);provenance=[]
    # GEOS is dynamically loaded and replaceable in the installed/expanded app.
    import shapely
    geos=shapely.geos_version_string
    for name,url in {
        f'geos-{geos}.tar.gz':f'https://codeload.github.com/libgeos/geos/tar.gz/refs/tags/{geos}',
        f'shapely-{shapely.__version__}.tar.gz':f'https://codeload.github.com/shapely/shapely/tar.gz/refs/tags/{shapely.__version__}'
    }.items():provenance.append(download(url,sources/name))
    # Exact PyInstaller source includes its bootloader and bundling exception.
    info=json.load(urllib.request.urlopen('https://pypi.org/pypi/pyinstaller/'+metadata.version('pyinstaller')+'/json',timeout=45))
    item=next(x for x in info['urls'] if x['packagetype']=='sdist');provenance.append(download(item['url'],sources/item['filename'],item['digests']['sha256']))
    inventory.append(dict(name='GEOS',version=geos,license='LGPL-2.1',scope='replaceable DLLs in core; corresponding source included'))
    (dest/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (sources/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(f'Collected {len(inventory)} dependency records and {len(provenance)} source archives')

if __name__=='__main__':main()
