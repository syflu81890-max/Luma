// Runs the actual renderer, preload, JSON-RPC and media protocol in an isolated profile.
const {app}=require('electron');const fs=require('node:fs'),os=require('node:os'),path=require('node:path');const {spawnSync}=require('node:child_process');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'luma-v02-smoke-'));app.commandLine.appendSwitch('lang','zh-CN');app.setPath('userData',root);process.argv.push('--background');
const python=path.join(__dirname,'../.venv/Scripts/python.exe');process.env.LUMA_PYTHON=python;
const seed=spawnSync(python,[path.join(__dirname,'seed_fixture.py'),root],{encoding:'utf8',windowsHide:true});if(seed.status!==0)throw Error(seed.stderr);
let done=false;const output=path.join(__dirname,'../output');fs.mkdirSync(output,{recursive:true});
app.on('browser-window-created',(_e,w)=>{
 w.webContents.on('console-message',event=>console.log('RENDERER',event.message));
 w.webContents.once('did-finish-load',async()=>{
  try{
   await new Promise(r=>setTimeout(r,900));
   const result=await w.webContents.executeJavaScript(`(async()=>{
     const s=await window.luma.call('stats');if(s.total!==5)throw Error('fixture total '+s.total);
     const list=await window.luma.call('list',{});if(list.items.length!==5)throw Error('page did not load');
     const accounts=await window.luma.call('accounts',{});if(accounts.items[0].rating!==4)throw Error('account rating missing');
     const f=await window.luma.call('list',{accountCategory:'穿搭',accountRating:'4+'});if(f.total!==4)throw Error('account filter mismatch');
     const photo=list.items.find(i=>i.kind==='image'),video=list.items.find(i=>i.kind==='video');
     const d=await window.luma.call('detail',{id:photo.id});if(!d.sources[0].content)throw Error('post text missing');
     const image=await fetch('luma://media/'+photo.id);if(!image.ok)throw Error('original protocol failed');
     const ranged=await fetch('luma://media/'+video.id,{headers:{Range:'bytes=0-31'}});const data=await ranged.arrayBuffer();
     if(ranged.status!==206||data.byteLength!==32)throw Error('video seeking/range unsupported '+ranged.status+' '+data.byteLength);
     return {total:s.total,account:accounts.items[0].id,video:video.id,range:ranged.status};
   })()`);
   fs.writeFileSync(path.join(output,'luma-v02-gallery.png'),(await w.webContents.capturePage()).toPNG());
   await w.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b=>b.textContent==='收集的账号').click()`);await new Promise(r=>setTimeout(r,600));fs.writeFileSync(path.join(output,'luma-v02-accounts.png'),(await w.webContents.capturePage()).toPNG());
   await w.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b=>b.textContent==='设置').click()`);await new Promise(r=>setTimeout(r,600));if(!(await w.webContents.executeJavaScript(`document.body.textContent.includes('资料库与存储')`)))throw Error('settings did not render');fs.writeFileSync(path.join(output,'luma-v02-settings.png'),(await w.webContents.capturePage()).toPNG());
   console.log('DESKTOP_SMOKE_OK',JSON.stringify(result));done=true;app.quit();
  }catch(e){console.error('DESKTOP_SMOKE_FAILED',e);done=true;process.exitCode=1;app.quit()}
 });
});
setTimeout(()=>{if(!done){console.error('Desktop smoke timed out');process.exitCode=1;app.quit()}},45000).unref();require('../electron/main.cjs');
