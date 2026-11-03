"""Offline OCR and Chinese image/text retrieval. Models never upload user media."""
import hashlib,json,threading,time
from pathlib import Path
from PIL import Image,ImageOps
from store import visual_hash

MODEL='chinese-clip-b16-q8-v1'
REV='f26904860903e70e050b8f48255e5f48401816e9'
BASE=f'https://huggingface.co/Xenova/chinese-clip-vit-base-patch16/resolve/{REV}/'
MODEL_SHA='a2c2849329eafb24100acec5a9421a39f8cb445296444c5c98855b69e5e7a751'
class Analyzer:
    def __init__(self,store):
        self.store=store;self.busy=False;self.closed=False;self.paused=True;self.session=None;self.tokenizer=None;self.ocr=None;self.message='分析已暂停';self.downloading=False;self.progress=0;self.error='';self.model_lock=threading.Lock();self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    @property
    def directory(self):return self.store.root/'models'/MODEL
    def status(self):
        total=self.store.query("SELECT COUNT(*) n FROM photos WHERE trash=0 AND kind='image'")[0]['n'];indexed=self.store.query('SELECT COUNT(*) n FROM embeddings e JOIN photos p ON p.id=e.photo WHERE e.model=? AND p.trash=0 AND p.kind=\'image\'',(MODEL,))[0]['n']
        return dict(paused=self.paused,busy=self.busy,message=self.message,error=self.error,downloading=self.downloading,downloadProgress=self.progress,modelReady=(self.directory/'ready.json').exists(),indexed=indexed,total=total,unindexed=max(0,total-indexed),pending=self.store.query("SELECT COUNT(*) n FROM photos WHERE trash=0 AND kind='image' AND analysis_status='pending'")[0]['n'])
    def install(self):
        if self.downloading:return self.status()
        self.downloading=True;self.error=''
        threading.Thread(target=self._install,daemon=True).start();return self.status()
    def _install(self):
        import requests,os
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            for filename in ['onnx/model_quantized.onnx','tokenizer.json']:
                path=self.directory/Path(filename).name;temp=Path(str(path)+'.part');digest=hashlib.sha256();downloaded=0
                self.message='正在下载本地中文搜图模型（约 191 MB）'
                with requests.get(BASE+filename,stream=True,timeout=(20,60)) as response:
                    response.raise_for_status();size=int(response.headers.get('Content-Length',0))
                    with temp.open('wb') as f:
                        for chunk in response.iter_content(1024*512):
                            if self.closed:raise RuntimeError('下载已中断，下次可重新安装')
                            if chunk:f.write(chunk);digest.update(chunk);downloaded+=len(chunk);self.progress=round(downloaded/max(size,190842404)*100)
                if filename.endswith('.onnx') and digest.hexdigest()!=MODEL_SHA:raise ValueError('模型校验失败，请重试')
                os.replace(temp,path)
            (self.directory/'ready.json').write_text(json.dumps({'model':MODEL,'sha256':MODEL_SHA,'revision':REV}),encoding='utf-8');self.progress=100;self.message='模型已就绪';self.paused=False
        except Exception as exc:self.error=str(exc);self.message='模型下载失败，图库仍可使用'
        finally:self.downloading=False
    def load(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        if self.session is None:
            if not (self.directory/'ready.json').exists():raise ValueError('请先在设置中安装中文搜图模型')
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            self.session=ort.InferenceSession(str(self.directory/'model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider']);self.tokenizer=Tokenizer.from_file(str(self.directory/'tokenizer.json'));self.tokenizer.enable_truncation(max_length=52)
    def encode(self,text='',image=None):
        import numpy as np
        with self.model_lock:
            self.load();encoding=self.tokenizer.encode(text or '图片');pixels=image if image is not None else Image.new('RGB',(224,224),'white')
            pixels=ImageOps.exif_transpose(pixels).convert('RGB').resize((224,224),Image.Resampling.BICUBIC)
            array=np.asarray(pixels,dtype=np.float32)/255.;array=(array-np.array([.48145466,.4578275,.40821073],dtype=np.float32))/np.array([.26862954,.26130258,.27577711],dtype=np.float32)
            inputs={'input_ids':np.array([encoding.ids],dtype=np.int64),'attention_mask':np.array([encoding.attention_mask],dtype=np.int64),'token_type_ids':np.array([encoding.type_ids],dtype=np.int64),'pixel_values':array.transpose(2,0,1)[None]}
            feed={i.name:inputs[i.name] for i in self.session.get_inputs()};outputs=dict(zip([o.name for o in self.session.get_outputs()],self.session.run(None,feed)))
            vector=outputs['image_embeds' if image is not None else 'text_embeds'][0].astype(np.float32);return vector/(np.linalg.norm(vector)+1e-12)
    def search(self,a):
        import numpy as np
        if a.get('photo'):
            paths=self.store.file_paths([a['photo']])
            if not paths:raise ValueError('原图不可用')
            with Image.open(paths[0]) as im:query=self.encode(image=im)
        else:query=self.encode(text=str(a.get('text','')))
        allowed=set(self.store.select_ids(a.get('filters',{})));rank=[]
        for row in self.store.query('SELECT photo,vector FROM embeddings WHERE model=?',(MODEL,)):
            if row['photo'] in allowed:rank.append((row['photo'],float(np.dot(query,np.frombuffer(row['vector'],dtype=np.float32)))))
        rank.sort(key=lambda r:r[1],reverse=True);ids=[r[0] for r in rank[:int(a.get('limit',120))]]
        page=self.store.list_photos({**a.get('filters',{}),'ids':ids,'limit':120});byid={p['id']:p for p in page['items']};page['items']=[dict(byid[ident],similarity=round(score,4)) for ident,score in rank[:len(ids)] if ident in byid];page['total']=len(ids);return page
    def analyze_one(self,row):
        import numpy as np
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
        with self.store.lock:
            paths=self.store.file_paths([row['id']])
            if not paths:raise FileNotFoundError('原文件不存在')
            im=Image.open(paths[0]);im.load()
        with im:
            im=ImageOps.exif_transpose(im).convert('RGB');phash=visual_hash(im);sample=im.copy();sample.thumbnail((1280,1280));results,_=self.ocr(np.asarray(sample))
            words=[];area=0
            for box,text,confidence in results or []:
                if float(confidence)<.65:continue
                words.append(text);xs=[p[0] for p in box];ys=[p[1] for p in box];area+=(max(xs)-min(xs))*(max(ys)-min(ys))
            letters=sum(len(w) for w in words);coverage=min(1,area/(sample.width*sample.height));colors=np.asarray(sample.resize((128,128)),dtype=np.float32);flatness=float(np.mean(np.std(colors,axis=2)<12));score=0.
            if letters>=12 and len(words)>=3:score=min(.99,coverage*1.8+min(letters/150,.35)+flatness*.18)
            self.store.write("UPDATE photos SET phash=?,ocr_text=?,text_score=?,analysis_status='done' WHERE id=?",(phash,'\n'.join(words),score,row['id']))
            if (self.directory/'ready.json').exists():
                vector=self.encode(image=im);self.store.write('INSERT OR REPLACE INTO embeddings VALUES(?,?,?)',(row['id'],MODEL,vector.tobytes()))
    def loop(self):
        while not self.closed:
            if self.paused:time.sleep(.4);continue
            try:
                rows=self.store.query("SELECT id,path FROM photos WHERE trash=0 AND kind='image' AND analysis_status='pending' ORDER BY created DESC LIMIT 1")
                if not rows and (self.directory/'ready.json').exists():rows=self.store.query("SELECT p.id,p.path FROM photos p WHERE trash=0 AND kind='image' AND NOT EXISTS(SELECT 1 FROM embeddings e WHERE e.photo=p.id AND e.model=?) LIMIT 1",(MODEL,))
                if not rows:self.message='现有照片分析完成';time.sleep(1);continue
                self.message='正在本地分析照片'
                with self.store.lock:
                    if self.paused or self.closed:continue
                    self.busy=True
                try:self.analyze_one(rows[0]);self.error=''
                finally:self.busy=False
                time.sleep(.1)
            except Exception as exc:
                self.error=str(exc);self.message='分析遇到问题，已暂停；图库仍可使用';self.paused=True
