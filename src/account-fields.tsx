import React,{useEffect,useState} from 'react';
import {Globe2} from 'lucide-react';
import countries from 'flag-icons/country.json';
import {api,Account} from './api';
import {locale,tr} from './i18n';
import {Modal} from './components';
import {Run} from './controls';

export type AccountCollection={id:string;name:string};
export function CollectionPicker({value,onChange,collections,onCollections}:{value:string;onChange:(value:string)=>void;collections:AccountCollection[];onCollections:(items:AccountCollection[])=>void}){
 const [slot,setSlot]=useState<number|null>(null),[name,setName]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const selected=value.split(',').filter(Boolean);
 const choose=(index:number,next:string)=>{const values=[...selected.slice(0,3)];values[index]=next;onChange([...new Set(values.filter(Boolean))].join(','))};
 return <><div className="collection-selectors">{[0,1,2].map(index=><select key={index} aria-label={tr('账号合集 {0}',[index+1])} value={selected[index]||''} onChange={e=>{if(e.target.value==='__new__'){setSlot(index);setName('');setError('')}else choose(index,e.target.value)}}><option value="">{tr('选择合集 {0}',[index+1])}</option>{collections.filter(c=>!selected.includes(c.name)||selected[index]===c.name).map(c=><option key={c.id} value={c.name}>{c.name}</option>)}<option value="__new__">＋ {tr('新建合集')}</option></select>)}</div>{selected.length>3&&<p className="hint">{tr('原有多个合集已保留；重新选择时最多保留 3 个。')}</p>}{slot!==null&&<Modal title={tr('新建合集')} close={()=>!saving&&setSlot(null)}><label>{tr('合集名称')}<input autoFocus aria-label={tr('新合集名称')} value={name} maxLength={80} onChange={e=>setName(e.target.value)}/></label>{error&&<p className="error-text">{error}</p>}<div className="modal-footer"><button className="primary" disabled={!name.trim()||saving} onClick={async()=>{setSaving(true);try{const result=await api('collectionAction',{action:'create',name:name.trim()});const items=await api<AccountCollection[]>('collections');onCollections(items);choose(slot,items.find(c=>c.id===result.id)?.name||name.trim());setSlot(null)}catch(e){setError((e as Error).message)}finally{setSaving(false)}}}>{tr('创建并选择')}</button></div></Modal>}</>
}

export function NoteShortcuts({value,onChange}:{value:string;onChange:(text:string)=>void}){
 const [items,setItems]=useState<any[]>([]);useEffect(()=>{api<any[]>('notePresets').then(setItems).catch(()=>{})},[]);
 return <div className="note-shortcuts"><small>{tr('常用备注')}</small>{items.length?items.map(item=><button key={item.text} type="button" title={item.text} onClick={()=>{if(!value.split('\n').includes(item.text))onChange(value.trim()?value.trimEnd()+'\n'+item.text:item.text);api('notePresetUse',{text:item.text}).then(setItems).catch(()=>{})}}>{item.text.length>28?item.text.slice(0,28)+'…':item.text}</button>):<span className="hint">{tr('保存过的简短备注会显示在这里，点击可追加。')}</span>}</div>
}

const regionNames=()=>new Intl.DisplayNames([locale()],{type:'region'});
export function CountryBadge({account,onClick}:{account:Account;onClick?:()=>void}){
 const code=account.country==='--'?'':account.country||account.suggested_country||'';let label=code?regionNames().of(code)||code:tr('设置国家或地区');
 if(!account.country&&code)label+=' · '+tr('根据常用语言建议，可修改');
 return <button className="country-badge" title={label} aria-label={label} onClick={e=>{e.stopPropagation();onClick?.()}}>{code?<span className={'fi fi-'+code.toLowerCase()}/>:<Globe2 size={15}/>}</button>
}
export function CountrySelect({account,onChange}:{account:Account;onChange:(code:string)=>void}){
 const names=regionNames();const options=countries.filter(c=>c.iso).map(c=>({code:c.code.toUpperCase(),name:names.of(c.code.toUpperCase())||c.name})).sort((a,b)=>a.name.localeCompare(b.name,locale()));
 return <label>{tr('国家或地区')}<select aria-label={tr('账号国家或地区')} value={account.country||''} onChange={e=>onChange(e.target.value)}><option value="">{tr('自动语言建议 / 未设置')}</option><option value="--">{tr('不显示旗帜')}</option>{options.map(c=><option key={c.code} value={c.code}>{c.name}</option>)}</select><small className="hint">{tr('语言建议不代表已确认的国籍，手动选择优先。')}</small></label>
}

export function AccountRemoval({account,close,run,removed}:{account:Account;close:()=>void;run:Run;removed:()=>void}){
 const [plan,setPlan]=useState<any>(null),[confirm,setConfirm]=useState(''),[trash,setTrash]=useState(true),[error,setError]=useState('');
 useEffect(()=>{api('accountRemovePlan',{id:account.id}).then(setPlan).catch(e=>setError(e.message))},[account.id]);
 return <Modal title={tr('删除账号及采集记录')} close={close}><p>{tr('将删除 @{0} 的资料、任务、合集关联和身份历史。',[account.handle])}</p>{plan&&<p className="notice">{tr('关联媒体 {0} 项，其中 {1} 项被其他账号共用；共用媒体保留。',[plan.media,plan.shared])}</p>}<label className="checkbox"><input type="checkbox" checked={trash} onChange={e=>setTrash(e.target.checked)}/>{tr('同时将仅属于此账号的媒体移入回收站')}</label><p className="hint">{tr('不会清空回收站，删除排除记录保留。完成后可用撤销恢复账号；恢复的任务保持暂停。')}</p><label>{tr('输入账号名确认')}<input aria-label={tr('输入账号名确认')} value={confirm} placeholder={'@'+account.handle} onChange={e=>setConfirm(e.target.value)}/></label>{error&&<p className="error-text">{error}</p>}<div className="modal-footer"><button className="subtle" onClick={close}>{tr('取消')}</button><button className="danger-button" disabled={!plan||confirm.replace(/^@/,'').toLowerCase()!==account.handle.toLowerCase()} onClick={()=>run(async()=>{await api('accountRemove',{id:account.id,confirmHandle:confirm,trashExclusive:trash});removed();close()})}>{tr('确认删除账号')}</button></div></Modal>
}
