// Explicit opt-in only: validates one already-known post using the user's normal app session.
if(process.env.LUMA_LIVE_VALIDATE!=='1')throw Error('Requires LUMA_LIVE_VALIDATE=1');
const {app,clipboard,ClipboardItem,nativeImage}=require('electron');const path=require('node:path');app.setPath('userData',path.join(app.getPath('appData'),'luma-x-library'));process.argv.push('--background');process.env.LUMA_PYTHON=path.join(__dirname,'../.venv/Scripts/python.exe');
if(process.env.LUMA_SKIP_NETWORK==='1')process.env.LUMA_RECOVERY_VERIFY='1';
let done=false;
app.on('browser-window-created',(_event,w)=>w.webContents.once('did-finish-load',async()=>{
 try{
  const before=await w.webContents.executeJavaScript(`(async()=>{const s=await window.luma.call('stats');const p=await window.luma.call('list',{kind:'image',limit:1});const d=await window.luma.call('detail',{id:p.items[0].id});return {total:s.total,photo:p.items[0],url:d.sources[0]?.url,loggedIn:(await window.luma.call('loginStatus')).loggedIn}})()`);
  console.log('LIVE_UPGRADE_LIBRARY',JSON.stringify({total:before.total,loggedIn:before.loggedIn}));
  if(before.url&&process.env.LUMA_SKIP_NETWORK!=='1'){
   const task=await w.webContents.executeJavaScript(`window.luma.call('addTask',${JSON.stringify({url:before.url,mode:'history',limit:1,options:{kinds:['image','video','gif']}})})`);let last='';const deadline=Date.now()+100000;
   while(Date.now()<deadline){const rows=await w.webContents.executeJavaScript(`window.luma.call('tasks')`);const t=rows.find(r=>r.id===task.id);if(t&&t.status!==last){console.log('LIVE_TASK',JSON.stringify({status:t.status,imported:t.imported,duplicates:t.duplicates,message:t.message}));last=t.status}if(t&&!['running','queued'].includes(t.status))break;await new Promise(r=>setTimeout(r,1000))}
  }
  const oldItems=await clipboard.read(),saved=[];
  for(const item of oldItems){const formats={};for(const type of item.types){try{formats[type]=await item.getType(type)}catch{}}if(Object.keys(formats).length)saved.push(new ClipboardItem(formats))}
  try{
   await w.webContents.executeJavaScript(`window.luma.call('copyImage',{id:${JSON.stringify(before.photo.id)}})`);const imageItem=(await clipboard.read()).find(i=>i.types.includes('image/png'));if(!imageItem)throw Error('Clipboard PNG is missing');const blob=await imageItem.getType('image/png');const size=nativeImage.createFromBuffer(Buffer.from(await blob.arrayBuffer())).getSize();if(!size.width)throw Error('Clipboard image is empty');console.log('CLIPBOARD_ORIGINAL',JSON.stringify(size));await w.webContents.executeJavaScript(`window.luma.call('copyFiles',{ids:[${JSON.stringify(before.photo.id)}]})`);console.log('CLIPBOARD_FILES_OK',JSON.stringify((await clipboard.read()).flatMap(i=>i.types)))
  }finally{if(saved.length)await clipboard.write(saved);else clipboard.clear()}
  console.log('LIVE_UPGRADE_OK');done=true;app.quit();
 }catch(e){console.error('LIVE_UPGRADE_FAILED',e.message);done=true;app.quit()}
}));
setTimeout(()=>{if(!done){console.error('LIVE_UPGRADE_TIMEOUT');app.quit()}},120000).unref();require('../electron/main.cjs');
