// Exercise actual preview geometry in an isolated desktop profile, including UI zoom.
const {app}=require('electron');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'luma-preview-'));
app.commandLine.appendSwitch('lang','zh-CN');app.setPath('userData',root);process.argv.push('--background');
const python=path.join(__dirname,'../.venv/Scripts/python.exe');process.env.LUMA_PYTHON=python;
const seed=spawnSync(python,[path.join(__dirname,'seed_fixture.py'),root],{encoding:'utf8',windowsHide:true});
if(seed.status!==0)throw Error(seed.stderr);
const output=path.join(__dirname,'../output');fs.mkdirSync(output,{recursive:true});
let done=false;
app.on('browser-window-created',(_e,w)=>{
 w.webContents.setBackgroundThrottling(false);
 w.webContents.once('did-finish-load',async()=>{
  const js=code=>w.webContents.executeJavaScript(code);
  const frame=()=>js('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  try{
   await js(`(async()=>{for(let i=0;i<200;i++){if(document.querySelector('.nav'))return;await new Promise(r=>setTimeout(r,50))}throw Error('App bootstrap timeout')})()`);
   await js(`[...document.querySelectorAll('.nav')].find(b=>b.textContent.startsWith('全部媒体')).click()`);
   await js(`(async()=>{for(let i=0;i<100;i++){if(document.querySelectorAll('.photo-card').length===5)return;await new Promise(r=>setTimeout(r,100))}throw Error('Gallery never loaded')})()`);
   const list=await js(`window.luma.call('list',{})`);
   const portrait=list.items.findIndex(p=>p.width===1080),landscape=list.items.findIndex(p=>p.width===1920),video=list.items.findIndex(p=>p.kind==='video');
   const results=[];
   for(const scenario of [{width:1280,height:800,zoom:1,font:1},{width:1920,height:1080,zoom:1.5,font:1.3},{width:3840,height:2160,zoom:1,font:1.6},{width:1000,height:640,zoom:2,font:1.6}]){
    w.setContentSize(scenario.width,scenario.height);w.webContents.setZoomFactor(scenario.zoom);
    await js(`document.documentElement.style.setProperty('--font-scale',${JSON.stringify(String(scenario.font))})`);await frame();
    for(const index of [portrait,landscape,video]){
     console.log('PREVIEW_CASE',JSON.stringify(scenario),list.items[index].kind,index);
     await js(`document.querySelectorAll('.photo-card')[${index}].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))`);await frame();
     const fit=await js(`(async()=>{
      const box=selector=>document.querySelector(selector).getBoundingClientRect();
      const toolbar=box('.viewer-toolbar'),stage=box('.viewer-stage'),content=box('.viewer-content'),caption=box('.viewer-caption');
      const img=document.querySelector('.viewer-media>img'),video=document.querySelector('.video-viewer video');
      if(img)await img.decode();else await new Promise((resolve,reject)=>{if(video.readyState>=1)return resolve();const timer=setTimeout(()=>reject(Error('Video metadata timeout: '+video.networkState+' / '+video.readyState)),10000);video.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve()},{once:true});video.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Video did not load'))},{once:true})});
      const media=(img||video).getBoundingClientRect();
      if(toolbar.top<0||toolbar.height>Math.max(160,innerHeight*.25)||stage.top<toolbar.bottom-1||stage.bottom>caption.top+1||caption.bottom>innerHeight+1||stage.height<innerHeight*.45)throw Error('Controls displaced preview '+JSON.stringify({toolbar:toolbar.toJSON(),stage:stage.toJSON(),caption:caption.toJSON(),height:innerHeight}));
      if(media.width<20||media.height<20||media.top<content.top-1||media.bottom>content.bottom+1||media.left<content.left-1||media.right>content.right+1)throw Error('Fitted media is clipped '+JSON.stringify({media:media.toJSON(),content:content.toJSON()}));
      for(const button of document.querySelectorAll('.viewer-toolbar button')){const b=button.getBoundingClientRect();if(b.right>innerWidth+1||b.left<0)throw Error('Toolbar control is unreachable')}
      return {viewport:[innerWidth,innerHeight],stageHeight:Math.round(stage.height),media:[Math.round(media.width),Math.round(media.height)]};
     })()`);
     if(index===portrait){
      if(scenario.width===1920)fs.writeFileSync(path.join(output,'luma-0.2.1-preview.png'),(await w.webContents.capturePage()).toPNG());
      await js(`[...document.querySelectorAll('.viewer-toolbar button')].find(b=>b.textContent==='100%').click()`);await frame();
      await js(`(()=>{const img=document.querySelector('.viewer-media>img'),c=document.querySelector('.viewer-content');if(Math.abs(img.getBoundingClientRect().width-img.naturalWidth)>1)throw Error('100% size mismatch');c.scrollTop=c.scrollHeight;c.scrollLeft=c.scrollWidth;if(c.scrollHeight>c.clientHeight+1&&c.scrollTop===0)throw Error('Cannot scroll vertically');if(c.scrollWidth>c.clientWidth+1&&c.scrollLeft===0)throw Error('Cannot scroll horizontally')})()`);
      await js(`(()=>{const input=document.querySelector('[aria-label="大图缩放"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'3');input.dispatchEvent(new Event('input',{bubbles:true}))})()`);await frame();
      await js(`(()=>{const img=document.querySelector('.viewer-media>img');if(Math.abs(img.getBoundingClientRect().width-img.naturalWidth*3)>1)throw Error('Zoom slider did not resize original')})()`);
      await js(`[...document.querySelectorAll('.viewer-toolbar button')].find(b=>b.textContent==='适应窗口').click()`);await frame();
      await js(`(()=>{const c=document.querySelector('.viewer-content'),r=document.querySelector('.viewer-media>img').getBoundingClientRect();if(c.scrollTop||c.scrollLeft||r.bottom>c.getBoundingClientRect().bottom+1)throw Error('Fit did not reset scroll')})()`);
     }
     results.push({...scenario,kind:list.items[index].kind,fit});
     await js(`document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`);await frame();
     if(await js(`!!document.querySelector('.lightbox')`))throw Error('Escape did not close preview');
    }
   }
   console.log('PREVIEW_SMOKE_OK',JSON.stringify(results));done=true;app.quit();
  }catch(e){console.error('PREVIEW_SMOKE_FAILED',e);fs.writeFileSync(path.join(output,'preview-failure.png'),(await w.webContents.capturePage()).toPNG());done=true;process.exitCode=1;app.quit()}
 });
});
setTimeout(()=>{if(!done){console.error('Preview smoke timed out');process.exitCode=1;app.quit()}},90000).unref();
require('../electron/main.cjs');
