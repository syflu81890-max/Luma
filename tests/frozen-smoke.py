"""Exercise the frozen backend including OCR, ONNX and bundled video decoder."""
import base64,hashlib,io,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat
root=Path(__file__).resolve().parents[1];profile=root/'.tools'/('frozen-check-'+uuid.uuid4().hex[:8]);(profile/'library/models').mkdir(parents=True)
fixture=root/'.tools/model-test/text-card.png'
if not fixture.is_file():
    from PIL import Image,ImageDraw
    fixture.parent.mkdir(parents=True,exist_ok=True)
    card=Image.new('RGB',(800,480),'white');ImageDraw.Draw(card).text((70,160),'WHITE SHOES 2026',fill='black',font_size=48);card.save(fixture)
model=root/'.tools/model-test/models/chinese-clip-b16-q8-v1'
if model.exists():shutil.copytree(model,profile/'library/models/chinese-clip-b16-q8-v1')
process=subprocess.Popen([str(root/'backend-dist/luma-backend/luma-backend.exe'),'--root',str(profile)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));serial=0
def call(method,args=None):
    global serial
    serial+=1;process.stdin.write(json.dumps(dict(id=serial,method=method,args=args or {}))+'\n');process.stdin.flush()
    while True:
        line=process.stdout.readline()
        if not line:raise RuntimeError('Frozen backend exited')
        try:r=json.loads(line)
        except ValueError:continue
        if r.get('id')==serial:
            if 'error' in r:raise RuntimeError(r['error'])
            return r['result']
try:
    result=call('import',dict(paths=[str(root/'.tools/model-test/text-card.png')]))
    assert result['added']==1,result
    call('analysis',dict(action='resume'));deadline=time.monotonic()+90;status={}
    while time.monotonic()<deadline:
        status=call('analysis')
        if status['error']:raise RuntimeError(status['error'])
        if status['pending']==0 and (not model.exists() or status['indexed']>0):break
        time.sleep(.4)
    assert status['pending']==0,status
    if model.exists():
        results=call('aiSearch',dict(text='\u767d\u8272\u8fd0\u52a8\u978b',filters={},limit=10));assert results['total']==1,results
    # The fixture generator uses its own ffmpeg; import is decoded by the frozen app.
    sys.path.insert(0,str(root/'backend'));from media_utils import ffmpeg_path
    video=profile/'clip.mp4';subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=1','-r','6','-c:v','mpeg4','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=30)
    result=call('import',dict(paths=[str(video)]));assert result['added']==1,result
    assert call('list',dict(kind='video'))['total']==1
    # A flat MPEG-4 frame does not expose H.264 optimized-decoder corruption.
    # Only the development fixture encoder uses imageio; the product still
    # decodes with its independent, source-built LGPL component.
    import imageio_ffmpeg
    pattern=Image.new('RGB',(720,1280));draw=ImageDraw.Draw(pattern)
    for index,color in enumerate([(210,45,35),(35,180,70),(40,80,210),(220,180,45)]):
        draw.rectangle((0,index*320,719,(index+1)*320-1),fill=color)
        for x in range(24,700,48):draw.rectangle((x,index*320+30,x+14,index*320+280),fill=tuple(c//2 for c in color))
    frame=profile/'pattern.png';pattern.save(frame);h264=profile/'portrait.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(frame),'-frames:v','2','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(h264)],check=True,capture_output=True,timeout=40)
    assert call('import',dict(paths=[str(h264)]))['added']==1
    ident=hashlib.sha256(h264.read_bytes()).hexdigest();poster=call('image',dict(id=ident))
    with Image.open(io.BytesIO(base64.b64decode(poster.split(',',1)[1]))) as decoded:
        expected=pattern.resize((360,640),Image.Resampling.BICUBIC)
        assert decoded.size==expected.size
        error=sum(ImageStat.Stat(ImageChops.difference(decoded.convert('RGB'),expected)).mean)/3
        assert error<10,('Corrupted frozen H.264 poster',error)
    print('FROZEN_SMOKE_OK',json.dumps(dict(ocr=True,indexed=status.get('indexed'),video=True,h264Poster=True,posterError=round(error,3),profile=str(profile))))
finally:
    try:call('shutdown')
    finally:process.stdin.close();process.wait(timeout=30)
