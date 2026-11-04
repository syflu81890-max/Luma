"""Check picture content, not only decoder exit codes or JPEG signatures."""
import base64,hashlib,io,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageChops,ImageStat
import imageio_ffmpeg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from media_utils import inspect_media
from store import Store

class VideoPosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory(prefix='luma-h264-pattern-')
        folder=Path(cls.fixture.name);cls.source=Image.new('RGB',(720,1280))
        draw=ImageDraw.Draw(cls.source)
        colors=[(210,45,35),(35,180,70),(40,80,210),(220,180,45)]
        for index,color in enumerate(colors):
            draw.rectangle((0,index*320,719,(index+1)*320-1),fill=color)
            for x in range(24,700,48):draw.rectangle((x,index*320+30,x+14,index*320+280),fill=tuple(c//2 for c in color))
        cls.expected=cls.source.resize((360,640),Image.Resampling.BICUBIC)
        image=folder/'pattern.png';cls.source.save(image);cls.video=folder/'pattern.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(image),'-frames:v','2','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(cls.video)],check=True,capture_output=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    @classmethod
    def tearDownClass(cls):
        cls.source.close();cls.expected.close();cls.fixture.cleanup()
    def assert_picture(self,image):
        self.assertEqual(image.size,self.expected.size)
        error=sum(ImageStat.Stat(ImageChops.difference(image.convert('RGB'),self.expected)).mean)/3
        self.assertLess(error,10,'H.264 cover has corrupted colors/scanlines')
    def test_h264_portrait_cover_preserves_colors_and_pattern(self):
        image,kind,duration,size=inspect_media(self.video)
        try:
            self.assert_picture(image);self.assertEqual(kind,'video');self.assertEqual(size,(720,1280));self.assertGreater(duration,0)
        finally:image.close()
    def test_legacy_corrupt_covers_are_rebuilt_once_for_video_and_mp4_gif(self):
        original_hash=hashlib.sha256(self.video.read_bytes()).hexdigest()
        for animated in (False,True):
            with self.subTest(animated=animated),tempfile.TemporaryDirectory(prefix='luma-poster-recovery-') as temp:
                store=Store(Path(temp)/'library')
                try:
                    store.ingest([self.video],metadata={'type':'animated_gif'} if animated else {})
                    row=store.list_photos({})['items'][0];ident=row['id'];store.edit({'ids':[ident],'note':'keep note'})
                    for cached in (store.root/'thumbs').glob(ident+'*'):cached.unlink()
                    legacy=store.root/'thumbs'/(ident+'.jpg');Image.new('RGB',(360,640),'magenta').save(legacy)
                    image=Image.open(io.BytesIO(base64.b64decode(store.image(ident).split(',',1)[1])))
                    self.assert_picture(image);image.close()
                    with patch('store.inspect_media',side_effect=AssertionError('re-decoded a current cover')):store.image(ident)
                    self.assertEqual(store.detail(ident)['note'],'keep note')
                    self.assertEqual(store.detail(ident)['kind'],'gif' if animated else 'video')
                    self.assertEqual(hashlib.sha256(Path(store.file_paths([ident])[0]).read_bytes()).hexdigest(),original_hash)
                    store.edit({'ids':[ident],'trash':1});store.purge([ident])
                    self.assertEqual(list((store.root/'thumbs').glob(ident+'*')),[])
                finally:store.db.close()
