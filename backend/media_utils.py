import io,os,re,subprocess,sys,uuid
from pathlib import Path
from PIL import Image,ImageOps
VIDEO_EXT={'.mp4','.webm','.mov','.mkv','.m4v'}
def thumbnail_name(ident,source):
    # Ignore posters made by the previous decoder, including MP4-backed GIFs.
    return ident+('.video-v2.jpg' if Path(source).suffix.lower() in VIDEO_EXT else '.jpg')
def save_thumbnail(image,target):
    target=Path(target);temporary=target.with_name(target.name+'.pending-'+uuid.uuid4().hex)
    try:
        with image.copy() as thumbnail:
            thumbnail.thumbnail((640,640));thumbnail.save(temporary,format='JPEG',quality=85)
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
def ffmpeg_path():
    base=Path(sys.executable).resolve().parent
    if getattr(sys,'frozen',False):
        candidates=[base.parent/'ffmpeg/ffmpeg.exe',base.parent.parent/'vendor/ffmpeg/ffmpeg.exe']
        for candidate in candidates:
            if candidate.is_file():return str(candidate)
        raise RuntimeError('视频组件不完整，请重新安装完整发行包')
    explicit=os.environ.get('LUMA_FFMPEG')
    if explicit and Path(explicit).is_file():return explicit
    vendor=Path(__file__).resolve().parents[1]/'vendor/ffmpeg/ffmpeg.exe'
    if vendor.is_file():return str(vendor)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
def inspect_media(path):
    path=Path(path)
    if path.suffix.lower() in VIDEO_EXT:
        # The Windows cross-build's optimized path can return success with
        # corrupted scanlines. Use portable CPU code for this one-frame job.
        result=subprocess.run([ffmpeg_path(),'-hide_banner','-cpuflags','0','-i',str(path),'-frames:v','1','-vf','scale=640:640:force_original_aspect_ratio=decrease','-f','image2pipe','-vcodec','mjpeg','pipe:1'],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not result.stdout:raise ValueError('无法读取视频封面')
        text=result.stderr.decode('utf-8',errors='replace');match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',text)
        duration=int(match[1])*3600+int(match[2])*60+float(match[3]) if match else 0
        size=re.search(r'Video:.*?\b(\d{2,6})x(\d{2,6})\b',text)
        im=Image.open(io.BytesIO(result.stdout)).convert('RGB');im.load()
        return im,'video',duration,(int(size[1]),int(size[2])) if size else im.size
    with Image.open(path) as original:
        original.load();kind='gif' if getattr(original,'is_animated',False) else 'image';duration=0
        if kind=='gif':
            for frame in range(original.n_frames):original.seek(frame);duration+=original.info.get('duration',100)/1000
            original.seek(0)
        im=ImageOps.exif_transpose(original).convert('RGB');im.load();return im,kind,duration,im.size
