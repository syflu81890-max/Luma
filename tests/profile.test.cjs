const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chooseProfile,prepareProfile}=require('../electron/profile.cjs');
const report=(profile,extra={})=>({profile,configured:false,photos:0,tasks:0,libraryPath:path.join(profile,'library'),databaseExists:true,error:'',...extra});
test('empty standalone profile finds configured legacy library and queue',()=>{
 const current=path.resolve('empty'),legacy=path.resolve('legacy'),r=report(legacy,{configured:true,libraryPath:path.resolve('E-library'),photos:7772,tasks:73});
 assert.equal(chooseProfile([report(current),r],current),r);
});
test('populated current library is preserved instead of silently replaced',()=>{
 const current=path.resolve('current'),a=report(current,{photos:2,tasks:3}),b=report(path.resolve('legacy'),{photos:7772,tasks:73});assert.equal(chooseProfile([a,b],current),a);
});
test('explicit legacy empty or offline location is preserved without a new empty library',()=>{
 const current=path.resolve('blank'),legacy=path.resolve('legacy'),chosen=report(legacy,{configured:true,databaseExists:false,libraryPath:path.resolve('offline-chosen')});assert.equal(chooseProfile([report(current),chosen],current),chosen);
 chosen.databaseExists=true;assert.equal(chooseProfile([report(current),chosen],current),chosen);
});
test('AppData alias selects explicit physical legacy profile',()=>{
 const current=path.resolve('logical'),a=report(current,{configured:true,photos:10,configIdentity:'same'}),b=report(path.resolve('physical'),{configured:true,photos:10,configIdentity:'same'});assert.equal(chooseProfile([a,b],current),b);
});
test('ambiguous or unreadable legacy libraries do not create an empty replacement',()=>{
 const current=path.resolve('current');assert.throws(()=>chooseProfile([report(current),report(path.resolve('one'),{photos:1}),report(path.resolve('two'),{tasks:2})],current),/多个旧资料库/);assert.throws(()=>chooseProfile([report(current,{error:'locked'})],current),/停止/);
});
test('copies settings/session locally, skips caches/media, commits once without changing source',()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'luma-profile-')),current=path.join(home,'empty'),legacy=path.join(home,'AppData/Local/Packages/OpenAI.Codex_test/LocalCache/Roaming/luma-x-library'),library=path.join(home,'external-library');
 fs.mkdirSync(path.join(legacy,'Partitions/luma-x/Network'),{recursive:true});fs.mkdirSync(path.join(legacy,'Cache'),{recursive:true});fs.mkdirSync(path.join(legacy,'library'),{recursive:true});
 const files={'desktop-settings.json':'{"zoom":1.1}','Local State':'local-test-state','Partitions/luma-x/Network/Cookies':'local-test-session','Cache/test':'not-copied','library/test':'not-copied'};
 for(const [file,value] of Object.entries(files))fs.writeFileSync(path.join(legacy,file),value);fs.writeFileSync(path.join(legacy,'library-location.json'),JSON.stringify({path:library}));
 const inspect=()=>[report(current),report(legacy,{configured:true,photos:7772,tasks:73,statuses:{queued:60},libraryPath:library})];
 const result=prepareProfile({current,home,inspect,snapshot:()=>{throw Error('External media should not be copied')}});
 assert.equal(result.migrated,true);assert.equal(result.info.tasks,73);assert.deepEqual(JSON.parse(fs.readFileSync(path.join(result.profile,'library-location.json'))),{path:library});
 assert.equal(fs.readFileSync(path.join(result.profile,'Partitions/luma-x/Network/Cookies'),'utf8'),'local-test-session');assert.ok(!fs.existsSync(path.join(result.profile,'Cache')));assert.ok(!fs.existsSync(path.join(result.profile,'library')));
 for(const [file,value] of Object.entries(files))assert.equal(fs.readFileSync(path.join(legacy,file),'utf8'),value);
 const again=prepareProfile({current,home,inspect:()=>{throw Error('Must use committed canonical profile')},snapshot:()=>{}});assert.equal(again.migrated,false);assert.equal(again.profile,result.profile);
});
test('fresh install explicitly permits only its initial empty library creation',()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'luma-fresh-')),current=path.join(home,'empty');const result=prepareProfile({current,home,inspect:()=>[report(current,{databaseExists:false})],snapshot:()=>{}});
 const config=JSON.parse(fs.readFileSync(path.join(result.profile,'library-location.json')));assert.equal(config.createIfMissing,true);assert.equal(config.path,path.join(result.profile,'library'));
});
test('failed copy keeps original profile and does not commit a new profile',()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'luma-failed-')),current=path.join(home,'original');fs.mkdirSync(current);fs.writeFileSync(path.join(current,'Local State'),'keep');
 assert.throws(()=>prepareProfile({current,home,inspect:()=>[report(current,{photos:3})],snapshot:()=>{throw Error('snapshot interrupted')}}),/snapshot interrupted/);
 assert.ok(!fs.existsSync(path.join(home,'.luma-desktop/UserData')));assert.equal(fs.readFileSync(path.join(current,'Local State'),'utf8'),'keep');
});
