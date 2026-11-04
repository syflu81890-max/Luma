"""Export only reviewed project sources and corresponding third-party materials."""
import argparse,hashlib,json,re,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','README.zh-CN.md','LICENSE','COPYRIGHT','CONTRIBUTING.md','SECURITY.md','THIRD_PARTY_NOTICES.md','package.json','package-lock.json','requirements.txt','requirements-build.lock','tsconfig.json','vite.config.ts','index.html','.gitignore','.gitattributes'}
SOURCE_DIRS={'src','electron','backend','collector','locales','tools','tests','.github'}
DOCS={'BUILDING.md','PRIVACY.md','SOURCE_CODE.md','TRANSLATING.md','LOCAL_ASSISTANT.md','THEME_INTERFACE.md','RELEASE_NOTES_0.5.1-beta.1.md','VALIDATION_0.5.1-beta.1.md'}
EXTENSIONS={'.py','.cjs','.js','.ts','.tsx','.css','.json','.md','.yml','.yaml','.sh','.txt','.html'}

def source_files():
    result=[]
    for name in ROOT_FILES:
        path=ROOT/name
        if not path.is_file():raise RuntimeError('Missing required source: '+name)
        result.append(path)
    for folder in SOURCE_DIRS:
        for path in (ROOT/folder).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:continue
            if path.suffix not in EXTENSIONS and path.name!='LICENSE':continue
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):raise RuntimeError('Unsafe source path')
            result.append(path)
    version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
    for name in DOCS|{f'RELEASE_NOTES_{version}.md',f'VALIDATION_{version}.md'}:
        path=ROOT/'docs'/name
        if path.is_file():result.append(path)
    result.append(ROOT/'build-resources/icon.ico')
    for path in (ROOT/'docs/images').glob('public-*.png'):result.append(path)
    result=sorted(set(result))
    # Fail closed for personal paths, secrets and generated user data. Public
    # project handles, localhost test fixtures and documentation examples are OK.
    prohibited=[r'(?i)[CE]:[\\/]+Users[\\/]+Luu',r'(?i)E:[\\/]+BaiduNetdiskDownload',r'(?i)[a-z0-9._%+-]+@(?:gmail\.com|qq\.com|outlook\.com|hotmail\.com|icloud\.com|yahoo\.com|163\.com|126\.com)\b',r'gh[pousr]_[A-Za-z0-9]{30,}',r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----']
    for path in result:
        if path.suffix in {'.png','.ico'}:continue
        text=path.read_text(encoding='utf-8-sig')
        if any(re.search(pattern,text) for pattern in prohibited):raise RuntimeError('Privacy check failed: '+path.relative_to(ROOT).as_posix())
    return result

def archive(target,files,prefix=''):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(set(files)):
            relative=path.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(prefix+relative,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,path.read_bytes())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest-only',action='store_true');args=parser.parse_args()
    version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version'];out=ROOT/'release-public';out.mkdir(exist_ok=True)
    sources=source_files();manifest=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sources]
    (ROOT/'output').mkdir(exist_ok=True);(ROOT/'output/public-source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if args.manifest_only:print(json.dumps(dict(sourceFiles=len(sources),bytes=sum(x['bytes'] for x in manifest))));return
    for name in ('LICENSE','COPYING.LGPLv2.1','ffmpeg.exe','BUILD.sh','config.h'):
        path=ROOT/'vendor/ffmpeg'/name
        if name=='LICENSE':continue
        if not path.is_file():raise RuntimeError('Missing FFmpeg material: '+name)
    if not (ROOT/'licenses/inventory.json').is_file():raise RuntimeError('Original license inventory missing')
    archives=list((ROOT/'third-party-sources').glob('*.tar.gz'))
    for stem in ('ffmpeg-','geos-','shapely-','pyinstaller-'):
        if not any(p.name.lower().startswith(stem) for p in archives):raise RuntimeError('Missing corresponding source: '+stem)
    binaries=[out/f'Luma-{version}-portable.exe',out/f'Luma-{version}-setup.exe']
    if not all(p.is_file() for p in binaries):raise RuntimeError('Both public Windows executables must exist')
    source_zip=out/f'Luma-{version}-source.zip';archive(source_zip,sources,f'Luma-{version}/')
    third_files=[p for folder in ('licenses','third-party-sources','vendor/ffmpeg') for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix not in {'.exe','.dll'}]
    third_files += [ROOT/'tools/build_ffmpeg.sh',ROOT/'tools/prepare_notices.py',ROOT/'requirements-build.lock',ROOT/'package-lock.json',ROOT/'THIRD_PARTY_NOTICES.md',ROOT/'docs/BUILDING.md',ROOT/'docs/SOURCE_CODE.md']
    third_zip=out/f'Luma-{version}-third-party-sources.zip';archive(third_zip,third_files)
    artifacts=binaries+[source_zip,third_zip]
    checksum=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts)
    (out/'SHA256SUMS.txt').write_text(checksum,encoding='utf-8')
    print(json.dumps(dict(version=version,sourceFiles=len(sources),artifacts=[dict(name=p.name,bytes=p.stat().st_size) for p in artifacts]),indent=2))

if __name__=='__main__':main()
