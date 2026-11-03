const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Workspaces}=require('../electron/workspaces.cjs'),{XSession,cookieSet}=require('../electron/x-session.cjs');
test('physical path aliases share one workspace and legacy IDs retain settings',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'luma-spaces-alias-'));
 try{
  const real=path.join(root,'physical'),alias=path.join(root,'alias'),profile=path.join(root,'profile');fs.mkdirSync(real);fs.mkdirSync(profile);fs.writeFileSync(path.join(real,'library.db'),'original');fs.symlinkSync(real,alias,process.platform==='win32'?'junction':'dir');
  const registry=new Workspaces(profile),first=registry.track(alias);assert.equal(registry.info(real).current.id,first.id);assert.equal(registry.items.length,1);
  fs.writeFileSync(path.join(profile,'workspaces.json'),JSON.stringify({version:1,items:[{id:'original-id',path:alias,name:'My references',appearance:{theme:'dark'}},{id:'duplicate-id',path:real,name:'Duplicate',appearance:{fontScale:1.3}}]}));
  const recovered=new Workspaces(profile);assert.equal(recovered.items.length,1);assert.equal(recovered.info(real).current.id,'original-id');assert.equal(recovered.info(alias).current.name,'My references');assert.deepEqual(recovered.get('duplicate-id').appearance,{theme:'dark',fontScale:1.3});assert.ok(fs.existsSync(path.join(profile,'workspaces.before-alias-dedupe.json')));assert.equal(new Workspaces(profile).get('duplicate-id').id,'original-id');assert.equal(fs.readFileSync(path.join(real,'library.db'),'utf8'),'original');
 }finally{fs.rmSync(root,{recursive:true,force:true})}
});
test('workspace names, paths and appearance survive restart without moving data',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'luma-spaces-'));try{
  const registry=new Workspaces(path.join(root,'profile')),one=path.join(root,'one'),two=path.join(root,'two');fs.mkdirSync(one);fs.mkdirSync(two);fs.writeFileSync(path.join(one,'library.db'),'original-one');fs.writeFileSync(path.join(two,'library.db'),'original-two');
  const first=registry.info(one).current;registry.save(one,{name:'日常收藏'});const second=registry.track(two);second.appearance={theme:'dark',fontScale:1.3};registry.write();
  const restored=new Workspaces(path.join(root,'profile'));assert.equal(restored.info(one).current.id,first.id);assert.equal(restored.info(one).current.name,'日常收藏');assert.equal(restored.info(two).current.appearance.fontScale,1.3);assert.notEqual(first.id,second.id);assert.equal(fs.readFileSync(path.join(one,'library.db'),'utf8'),'original-one');assert.equal(restored.info(two).themeInterface.active,'default');
  restored.save(one,{logo:path.join(root,'unrelated.txt')});assert.equal(restored.info(one).current.logo,'');
 }finally{fs.rmSync(root,{recursive:true,force:true})}
});
test('cookies respect applicable X domain and ignore expired/path-shadowed values',()=>{
 const now=Date.now()/1000;assert.deepEqual(cookieSet([{name:'auth_token',value:'expired',expirationDate:now-1},{name:'auth_token',value:'valid',path:'/'},{name:'ct0',value:'base',path:'/'},{name:'ct0',value:'api',path:'/i/api'},{name:'other',value:'never'}]),{auth_token:'valid',ct0:'api'});
});
test('identity uses authenticated account settings, caches and never returns credentials',async()=>{
 let calls=0;const fake={cookies:{get:async({url})=>url.includes('x.com')?[{name:'auth_token',value:'private-secret'},{name:'ct0',value:'csrf-secret'}]:[{name:'auth_token',value:'wrong-twitter-identity'}]},fetch:async(url,options)=>{calls++;assert.equal(options.credentials,'include');assert.equal(options.headers['x-csrf-token'],'csrf-secret');return {ok:true,json:async()=>({screen_name:'my_account'})}}};
 const session=new XSession(fake);assert.equal((await session.cookies()).auth_token,'private-secret');assert.deepEqual(await session.info(),{loggedIn:true,verified:true,handle:'my_account',message:'已验证当前 X 登录身份'});await session.info();assert.equal(calls,1);assert.doesNotMatch(JSON.stringify(await session.info()),/private-secret|csrf-secret|fingerprint/);
 fake.fetch=async()=>({ok:false,status:401});assert.equal((await session.info(true)).loggedIn,false);assert.deepEqual(await session.cookies(),{});
});
test('browser proxy configuration is shared with identity and rejects invalid schemes',async()=>{
 const configs=[],session=new XSession({setProxy:async value=>configs.push(value)});await session.configureProxy('socks5h://127.0.0.1:1080');assert.equal(configs[0].proxyRules,'socks5://127.0.0.1:1080');await session.configureProxy('socks5h://127.0.0.1:1080');assert.equal(configs.length,1);await session.configureProxy('');assert.equal(configs[1].mode,'system');await assert.rejects(()=>session.configureProxy('file:///private'),/无效/);
});
test('unverified profile and absent session are visible without pretending authentication passed',async()=>{
 const noCookies=new XSession({cookies:{get:async()=>[]}});assert.equal((await noCookies.info()).loggedIn,false);
 const limited=new XSession({cookies:{get:async()=>[{name:'auth_token',value:'fixture'}]},fetch:async()=>({ok:false,status:429})});const value=await limited.info();assert.equal(value.verified,false);assert.match(value.message,/受限/);
});
