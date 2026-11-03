// End-to-end HTTP -> Electron -> Python, with a separate profile and no network.
const {app,nativeImage}=require('electron'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'luma-assistant-desktop-'));app.commandLine.appendSwitch('lang','zh-CN');app.setPath('userData',root);process.argv.push('--background');process.env.LUMA_POWER_DRY_RUN='1';process.env.LUMA_RECOVERY_VERIFY='1';
const python=path.join(__dirname,'../.venv/Scripts/python.exe');process.env.LUMA_PYTHON=python;
fs.writeFileSync(path.join(root,'assistant-settings.json'),JSON.stringify({enabled:true,port:0}));
const seeded=spawnSync(python,[path.join(__dirname,'seed_fixture.py'),root],{encoding:'utf8',windowsHide:true});if(seeded.status)throw Error(seeded.stderr);
const output=path.join(__dirname,'../output');fs.mkdirSync(output,{recursive:true});let done=false;
app.on('browser-window-created',(_e,w)=>{w.webContents.setBackgroundThrottling(false);w.webContents.once('did-finish-load',async()=>{
 const js=code=>w.webContents.executeJavaScript(code);
 const wait=condition=>js(`(async()=>{for(let n=0;n<200;n++){if(${condition})return;await new Promise(r=>setTimeout(r,50))}throw Error('Timed out')})()`);
 try{
  await wait(`!!document.querySelector('.nav')`);
  await js(`[...document.querySelectorAll('.nav')].find(b=>b.textContent.startsWith('全部媒体')).click()`);
  await wait(`document.querySelectorAll('.photo-card').length===5`);
  const connection=JSON.parse(fs.readFileSync(path.join(root,'assistant-connection.json'),'utf8'));
  const call=async(method,args={})=>{const r=await fetch(connection.url+'/v1/rpc',{method:'POST',headers:{Authorization:'Bearer '+connection.token,'Content-Type':'application/json'},body:JSON.stringify({method,args})});const result=await r.json();if(result.error)throw Error(result.error);return result.result};
  const stats=await call('stats');if(stats.total!==5)throw Error('Wrong fixture');
  const list=await call('list',{kind:'image'}),id=list.items[0].id,files=await call('files',{ids:[id]});const before=fs.readFileSync(files[0]);
  const plan=await call('assistantPlan',{ids:[id],action:'tags',value:'助手整理测试'});await call('assistantApply',{id:plan.id});
  await wait(`!![...document.querySelectorAll('.photo-card .chips small')].find(e=>e.textContent==='助手整理测试')`);
  await call('assistantUndo',{id:plan.id});
  const job=await call('assistantEditPrepare',{ids:[id],prompt:'测试结果交接',references:[path.join(root,'fixture-1.png')]});
  const result=await call('assistantEditCommit',{id:job.id,index:0,path:path.join(root,'fixture-1.png')}).then(()=>null,e=>e.message);
  if(!result?.includes('已存在'))throw Error('Existing result was incorrectly reparented');
  const generated=path.join(root,'generated.png');fs.writeFileSync(generated,nativeImage.createFromBitmap(Buffer.alloc(40*60*4,230),{width:40,height:60}).toPNG());
  const committed=await call('assistantEditCommit',{id:job.id,index:0,path:generated});if(committed.parent!==id||!(await call('detail',{id:committed.photo})).sources.length)throw Error('Generated version/provenance missing');
  if(!fs.readFileSync(files[0]).equals(before))throw Error('Original was changed');
  const folder=await call('assistantFolder',{path:root,recursive:false});if(folder.items.length!==5)throw Error('Folder scan failed');
  await js(`[...document.querySelectorAll('button')].find(b=>b.textContent==='设置').click()`);await wait(`!!document.querySelector('.assistant-settings .path')`);
  await wait(`document.querySelector('.assistant-settings .path').textContent.startsWith('http://127.0.0.1:')`);
  w.setContentSize(1480,1050);await new Promise(r=>setTimeout(r,200));
  w.showInactive();await js(`document.querySelector('.assistant-settings').scrollIntoView({behavior:'instant',block:'center'})`);await new Promise(r=>setTimeout(r,500));
  const geometry=await js(`(()=>{const e=document.querySelector('.assistant-settings'),r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,scroll:document.querySelector('.library').scrollTop}})()`);if(geometry.top<80||geometry.bottom>windowHeight())throw Error('Assistant settings not visible '+JSON.stringify(geometry));
  fs.writeFileSync(path.join(output,'luma-0.3.2-assistant.png'),(await w.webContents.capturePage()).toPNG());w.hide();
  const client=await require('node:util').promisify(require('node:child_process').execFile)(python,[path.join(__dirname,'../tools/luma_assistant.py'),'--connection',path.join(root,'assistant-connection.json'),'status'],{encoding:'utf8',windowsHide:true,timeout:15000});if(JSON.parse(client.stdout).app!=='Luma')throw Error('Client failed: '+client.stderr);
  console.log('ASSISTANT_SMOKE_OK',JSON.stringify({http:true,uiRefresh:true,planUndo:true,existingVersionProtected:true,folder:true,client:true,media:stats.total,profile:root}));done=true;app.quit();
 }catch(e){console.error('ASSISTANT_SMOKE_FAILED',e);fs.writeFileSync(path.join(output,'assistant-failure.png'),(await w.webContents.capturePage()).toPNG());done=true;process.exitCode=1;app.quit()}
 })});
function windowHeight(){return 1050}
setTimeout(()=>{if(!done){console.error('Assistant smoke timed out');process.exitCode=1;app.quit()}},90000).unref();require('../electron/main.cjs');app.on('will-quit',()=>{if(process.exitCode)process.exit(process.exitCode)});
