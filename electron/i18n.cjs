const dictionary=require('../locales/en.json');
let current='zh-CN';
function setLanguage(value,system='zh-CN'){current=value==='en'?'en':value==='zh-CN'?'zh-CN':system.toLowerCase().startsWith('zh')?'zh-CN':'en'}
function tr(source,values=[]){const text=current==='en'?(dictionary[source]??source):source;return values.length?text.replace(/\{(\d+)\}/g,(_,i)=>String(values[+i]??'')):text}
module.exports={tr,setLanguage};
