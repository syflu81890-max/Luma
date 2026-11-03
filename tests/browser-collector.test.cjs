const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
function setup(){
 class FakeWindow extends EventEmitter{
  constructor(options){super();this.options=options;this.destroyed=false;this.webContents=new EventEmitter();this.webContents.setWindowOpenHandler=fn=>this.openHandler=fn;const debug=this.webContents.debugger=new EventEmitter();debug.attach=()=>{};debug.sendCommand=async name=>name==='Network.getResponseBody'?{body:JSON.stringify({data:{visible:'tweet'}}),base64Encoded:false}:{};}
  isDestroyed(){return this.destroyed}show(){}setTitle(value){this.title=value}async loadURL(url){this.url=url}destroy(){this.destroyed=true;this.emit('closed')}
 }
 const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../electron/browser-collector.cjs'),'utf8'),{require:name=>name==='electron'?{BrowserWindow:FakeWindow}:name==='./i18n.cjs'?require('../electron/i18n.cjs'):require(name),module,URL,Buffer,Promise,Set,Error});
 const calls=[];const parent={webContents:{send:(...args)=>calls.push(['notify',args])}};
 const rpc=async(method,args)=>{calls.push([method,args]);if(method==='browserTask')return {url:'https://x.com/fixture/status/123',account:'x:9'};if(method==='account')return {handle:'fixture',external_id:'9'};if(method==='browserPrepare')return {id:'capture-1'};if(method==='browserCandidates')return {total:3};return true};
 return {collector:new module.exports.BrowserCollector({parent,rpc}),calls};
}
test('browser collector uses same signed-in partition and captures authorized response bodies before finishing',async()=>{
 const {collector,calls}=setup();const result=await collector.start({id:'source'}),window=collector.window;assert.equal(result.id,'capture-1');assert.equal(window.options.webPreferences.partition,'persist:luma-x');assert.equal(window.options.webPreferences.nodeIntegration,false);assert.equal(window.openHandler().action,'deny');
 const debug=window.webContents.debugger;debug.emit('message',{},'Network.responseReceived',{requestId:'one',response:{status:200,url:'https://x.com/i/api/graphql/id/TweetDetail'}});debug.emit('message',{},'Network.loadingFinished',{requestId:'one'});
 await new Promise(r=>setImmediate(r));assert.match(window.title,/3/);const captured=calls.find(c=>c[0]==='browserCandidates')[1];assert.equal(captured.owner,'fixture');assert.equal(captured.ownerId,'9');assert.equal(captured.post,'123');assert.deepEqual(JSON.parse(JSON.stringify(captured.data)),{data:{visible:'tweet'}});
 window.destroy();await new Promise(r=>setImmediate(r));assert.equal(calls.filter(c=>c[0]==='browserFinish').length,1);assert.equal(collector.window,null);
});
test('browser collector ignores third-party and non-media endpoints and disallows navigation outside X',async()=>{
 const {collector,calls}=setup();await collector.start({id:'source'});const window=collector.window,debug=window.webContents.debugger;
 for(const url of ['https://elsewhere.test/i/api/graphql/id/UserMedia','https://x.com/i/api/graphql/id/Following','https://x.com/i/api/1.1/account/settings.json']){debug.emit('message',{},'Network.responseReceived',{requestId:url,response:{status:200,url}});debug.emit('message',{},'Network.loadingFinished',{requestId:url})}
 await new Promise(r=>setImmediate(r));assert.equal(calls.filter(c=>c[0]==='browserCandidates').length,0);let prevented=false;window.webContents.emit('will-navigate',{preventDefault:()=>prevented=true},'https://elsewhere.test');assert.equal(prevented,true);await assert.rejects(()=>collector.start({id:'another'}),/已有/);window.destroy();
});
test('double activation during startup opens a single capture window',async()=>{
 const {collector,calls}=setup();const first=collector.start({id:'source'});await assert.rejects(()=>collector.start({id:'source'}),/正在打开/);await first;assert.equal(calls.filter(c=>c[0]==='browserPrepare').length,1);collector.window.destroy();
});
