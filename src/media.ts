import {api} from './api';
const cache=new Map<string,Promise<string>>();
const waiting:Array<()=>void>=[];let active=0;
function pump(){while(active<4&&waiting.length){active++;waiting.shift()!()}}
export function cachedMedia(method:string,id:string,version=''){
 const key=[method,id,version].join(':');const found=cache.get(key);if(found)return found;
 const promise=new Promise<string>((resolve,reject)=>{waiting.push(()=>{api<string>(method,{id}).then(value=>{if(!value)cache.delete(key);resolve(value)},error=>{cache.delete(key);reject(error)}).finally(()=>{active--;pump()})});pump()});
 cache.set(key,promise);while(cache.size>240)cache.delete(cache.keys().next().value!);return promise;
}
