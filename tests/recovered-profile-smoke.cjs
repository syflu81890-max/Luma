// Explicit live recovery verification: no collection tick or system power action.
if(process.env.LUMA_LIVE_VALIDATE!=='1')throw Error('Requires LUMA_LIVE_VALIDATE=1');
const {app}=require('electron'),path=require('node:path');
app.commandLine.appendSwitch('lang','zh-CN');app.setPath('userData',path.join(app.getPath('appData'),'luma-x-library'));process.argv.push('--background');process.env.LUMA_RECOVERY_VERIFY='1';process.env.LUMA_POWER_DRY_RUN='1';process.env.LUMA_PYTHON=path.join(__dirname,'../.venv/Scripts/python.exe');
let done=false;
app.on('browser-window-created',(_event,w)=>w.webContents.once('did-finish-load',async()=>{
 try{
  const r=await w.webContents.executeJavaScript(`(async()=>{const s=await window.luma.call('stats'),p=await window.luma.call('profileInfo'),l=await window.luma.call('libraryLocation'),t=await window.luma.call('taskPage',{status:'all',limit:100}),auth=await window.luma.call('loginStatus');return {total:s.total,profile:p.profile,library:l.path,tasks:t.total,counts:t.counts,loggedIn:auth.loggedIn}})()`);
  if(r.total<7772||r.tasks<73||r.counts.queued!==60||r.counts.paused!==1||!r.profile.includes('.luma-desktop'))throw Error('Recovered data mismatch '+JSON.stringify(r));
  console.log('RECOVERED_PROFILE_SMOKE_OK',JSON.stringify(r));done=true;app.quit();
 }catch(e){console.error('RECOVERED_PROFILE_SMOKE_FAILED',e.message);done=true;process.exitCode=1;app.quit()}
}));
setTimeout(()=>{if(!done){console.error('Recovered profile smoke timeout');process.exitCode=1;app.quit()}},120000).unref();require('../electron/main.cjs');
