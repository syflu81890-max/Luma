let scope='default',legacy=false;
export function setWorkspaceScope(id:string,allowLegacy=false){scope=id;legacy=allowLegacy;document.documentElement.dataset.workspace=id;document.documentElement.dataset.skin='default'}
export function storageKey(key:string){return 'luma:'+scope+':'+key}
export function readStored<T>(key:string,initial:T):T{try{return JSON.parse(localStorage.getItem(storageKey(key))||(legacy?localStorage.getItem(key):'')||'null')??initial}catch{return initial}}
export function writeStored(key:string,value:unknown){localStorage.setItem(storageKey(key),JSON.stringify(value))}
