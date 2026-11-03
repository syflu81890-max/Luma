import english from '../locales/en.json';

export type Language='system'|'zh-CN'|'en';
const dictionary=english as Record<string,string>;
export function language():Language{try{return (localStorage.getItem('luma-language') as Language)||((window as any).luma?.language as Language)||'system'}catch{return 'system'}}
export function locale(){const value=language();return value==='system'?(((window as any).luma?.systemLocale||navigator.language).toLowerCase().startsWith('zh')?'zh-CN':'en'):value}
export function storeLanguage(value:Language){localStorage.setItem('luma-language',value);document.documentElement.lang=value==='system'?(navigator.language.startsWith('zh')?'zh-CN':'en'):value}
const patterns=Object.entries(dictionary).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>({pattern:new RegExp('^'+key.split(/\{\d+\}/).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('([\\s\\S]*?)')+'$'),value}));
export function tr(source:string,values:unknown[]=[]):string{
 let translated=source;
 if(locale()==='en'){
  translated=dictionary[source]??source;
  if(translated===source&&/\p{Script=Han}/u.test(source)){for(const item of patterns){const match=source.match(item.pattern);if(match){translated=item.value.replace(/\{(\d+)\}/g,(_,index)=>match[+index+1]??'');break}}}
 }
 return values.length?translated.replace(/\{(\d+)\}/g,(_,index)=>String(values[+index]??'')):translated;
}
export function serverText<T>(value:T):T{
 if(locale()!=='en'||value==null)return value;
 if(Array.isArray(value))return value.map(serverText) as T;
 if(typeof value!=='object')return value;
 const result:any={...value};for(const [key,item] of Object.entries(result)){
  if(['message','reason','error','offline','availability_reason'].includes(key)&&typeof item==='string')result[key]=tr(item);
  else if(item&&typeof item==='object')result[key]=serverText(item);
 }return result;
}

document.documentElement.lang=locale();
