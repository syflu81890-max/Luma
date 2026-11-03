import {CollectionPicker,NoteShortcuts,CountrySelect,CountryBadge} from './account-fields';
import { tr } from './i18n';
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, MoreHorizontal, Folder, ShieldAlert, Clock, Images, Star, Film, Check, Undo2 } from 'lucide-react';
import { api, Account, Stats, date, bytes } from './api';
import { Avatar, Empty, Modal, Pagination, RatingFilter } from './components';
import { Run, useStored } from './controls';
import { cachedMedia } from './media';
import { useMarquee } from './marquee';
export const ago = (value: string) => { if (!value)
    return tr("从未检查"); const hours = Math.max(0, (Date.now() - new Date(value).getTime()) / 3600000); return hours < 1 ? tr("刚刚检查") : hours < 24 ? tr("{0} 小时未检查", [Math.floor(hours)]) : tr("{0} 天未检查", [Math.floor(hours / 24)]); };
type Collection = {
    id: string;
    name: string;
    count: number;
    suspended: number;
};
export function AccountHistory({ account, close }: {
    account: Account;
    close: () => void;
}) {
    const [items, setItems] = useState<any[]>([]), [error, setError] = useState('');
    useEffect(() => { api<any[]>('accountHistory', { id: account.id }).then(setItems).catch(e => setError(e.message)); }, [account.id]);
    return <Modal title={tr("曾用名与头像")} wide close={close}><p className="hint">@{account.handle}{tr("· 保存软件观察到的变化和本地头像副本；更早的历史无法补回。")}</p>{error && <p className="error-text">{error}</p>}<div className="identity-history">{items.map(item => <div key={item.id}><HistoryAvatar id={item.id}/><strong>{item.name}</strong><span>@{item.handle}</span><small>{date(item.first_seen)}</small></div>)}</div>{!items.length && <p className="muted">{tr("还没有观察到身份变化。")}</p>}</Modal>;
}
function HistoryAvatar({ id }: {
    id: string;
}) { const [src, setSrc] = useState(''); useEffect(() => { let live = true; cachedMedia('historyAvatar', id).then(s => live && setSrc(s)).catch(() => { }); return () => { live = false; }; }, [id]); return <div className="history-avatar">{src ? <img src={src} alt={tr("历史头像")}/> : <Images size={22}/>}</div>; }
export function AccountEditor({ account, collections, close, run, changed }: {
    account: Account;
    collections: Collection[];
    close: () => void;
    run: Run;
    changed: () => void;
}) {
    const [available,setAvailable]=useState(collections);
    const [draft, setDraft] = useState(account), [history, setHistory] = useState(false), [revision, setRevision] = useState(0);
    return <><Modal title={tr("账号资料")} close={close}><div className="editor-identity"><Avatar account={draft} revision={revision}/><div><strong>{account.name || account.handle}</strong><p>@{account.handle}</p></div></div><div className="form-row"><label>{tr("备注名")}<input value={draft.alias} onChange={e => setDraft({ ...draft, alias: e.target.value })} placeholder={tr("用于卡片显示")}/></label><label>{tr("评分")}<select value={draft.rating} onChange={e => setDraft({ ...draft, rating: +e.target.value })}><option value="0">{tr("未评分")}</option>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{'★'.repeat(n)}</option>)}</select></label></div><label>{tr("账号合集")}</label><CollectionPicker value={draft.categories} onChange={categories=>setDraft({...draft,categories})} collections={available} onCollections={items=>{setAvailable(items as Collection[]);changed()}}/><CountrySelect account={draft} onChange={country=>setDraft({...draft,country})}/><p className="hint">{tr('别名用于显示和识别账号；备注记录内容特点和收藏理由。')}</p><label>{tr("私人备注")}<textarea value={draft.note} onChange={e => setDraft({ ...draft, note: e.target.value })}/></label><NoteShortcuts value={draft.note} onChange={note=>setDraft({...draft,note})}/><div className="button-row"><button className="subtle" onClick={() => run(async () => { await api('avatarDialog', { id: account.id }); setRevision(n => n + 1); changed(); })}>{tr("自定义头像")}</button><button className="subtle" onClick={() => run(async () => { await api('saveAccount', { id: account.id, custom_avatar: '' }); await api('refreshAvatar', { id: account.id }); setDraft(await api<Account>('account',{id:account.id})); setRevision(n => n + 1); changed(); })}>{tr("使用官方头像")}</button><button className="subtle" onClick={() => setHistory(true)}>{tr("曾用名与头像")}</button></div><div className="modal-footer"><button className="primary" onClick={() => run(async () => { await api('saveAccount', { id: draft.id, alias: draft.alias, note: draft.note, rating: draft.rating, categories: draft.categories, country:draft.country }); changed(); close(); })}>{tr("保存")}</button></div></Modal>{history && <AccountHistory account={account} close={() => setHistory(false)}/>}</>;
}
export function AccountsCards({ stats, open, collect, openTasks, run, initialPool = 'normal', initialStale = false }: {
    stats: Stats;
    open: (a: Account, kind?: string, batch?: string) => void;
    collect: (handle: string, mode?: string) => void;
    openTasks: (id: string) => void;
    run: Run;
    refresh?: number;
    initialPool?: string;
    initialStale?: boolean;
}) {
    const [page, setPage] = useStored('account-cards-page', 1), [size, setSize] = useStored('account-cards-size', 64), [pool, setPool] = useState(initialPool), [collection, setCollection] = useStored('account-cards-collection', ''), [rating, setRating] = useStored('account-cards-rating', 'all'), [sort, setSort] = useStored('account-cards-sort', 'name'), [stale, setStale] = useState(initialStale), [query, setQuery] = useStored('account-cards-query', ''), [search, setSearch] = useState(query), [data, setData] = useState<any>({ items: [], total: 0, pages: 1, page: 1, pools: {} }), [collections, setCollections] = useState<Collection[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [reload, setReload] = useState(0), [selected, setSelected] = useStored<string[]>('account-card-selected', []), [editor, setEditor] = useState<Account | null>(null), [history, setHistory] = useState<Account | null>(null), [menu, setMenu] = useState<any>(null), [hover, setHover] = useState<any>(null), [adding, setAdding] = useState(false), [value, setValue] = useState(''), [newCollection, setNewCollection] = useState(false), [rename, setRename] = useState<Collection | null>(null), [health, setHealth] = useState<any>({ status: 'idle' }), [message, setMessage] = useState('');
    const draggedCollection=useRef('');
    const reorderCollection=(target:string)=>{const source=draggedCollection.current;if(!source||source===target)return;const items=[...collections];const from=items.findIndex(c=>c.id===source),to=items.findIndex(c=>c.id===target);if(from<0||to<0)return;const moved=items.splice(from,1)[0];items.splice(to,0,moved);setCollections(items);run(async()=>setCollections(await api('collectionAction',{action:'reorder',ids:items.map(c=>c.id)})))};
    const lastSelected = useRef(''), generation = useRef(0), loaded = useRef(false), marquee = useMarquee(selected, setSelected), filters = { q: search, pool, collection, rating, sort, direction: sort === 'name' ? 'asc' : 'desc', staleDays: stale ? 7 : undefined }, key = JSON.stringify(filters);
    const changed = () => setReload(n => n + 1);
    useEffect(() => { const timer = setTimeout(() => setSearch(query), 250); return () => clearTimeout(timer); }, [query]);
    useEffect(() => { let live = true; if (!loaded.current)
        setLoading(true); const load = () => { const ticket = ++generation.current; api('accounts', { ...filters, page, limit: size }).then(d => { if (live && ticket === generation.current) {
        setData(d);
        loaded.current = true;
        setError('');
        setLoading(false);
    } }).catch(e => { if (live) {
        setError(e.message);
        setLoading(false);
    } }); }; load(); const timer = setInterval(load, 30000); return () => { live = false; clearInterval(timer); }; }, [key, page, size, reload]);
    useEffect(() => { api<Collection[]>('collections').then(setCollections).catch(() => { }); }, [reload]);
    useEffect(() => { const stop = (window.luma as any)?.onAssistantChanged?.(changed); return () => stop?.(); }, []);
    useEffect(() => { let live = true; const tick = () => api('accountHealthStatus').then(h => { if (!live)
        return; setHealth((old: any) => { if (old.status === 'running' && h.status === 'completed')
        changed(); return h; }); }).catch(() => { }); tick(); const timer = setInterval(tick, 3000); return () => { live = false; clearInterval(timer); }; }, []);
    useEffect(() => { if (!menu)
        return; const close = () => setMenu(null); window.addEventListener('click', close); window.addEventListener('scroll', close, true); return () => { window.removeEventListener('click', close); window.removeEventListener('scroll', close, true); }; }, [menu]);
    const reset = (fn: () => void) => { fn(); setPage(1); setSelected([]); setHover(null); };
    const check = (ids?: string[]) => run(async () => { setHealth(await api('accountHealthCheck', ids ? { ids } : {})); });
    const batch = (action: string, extra: any = {}) => run(async () => { const r = await api('accountBatch', { ids: selected, action, ...extra }); setMessage(tr("完成 {0} · 跳过 {1} · 需处理 {2}", [r.succeeded, r.skipped, r.errors.length])); changed(); });
    const context = (e: React.MouseEvent, a: Account) => { e.preventDefault(); e.stopPropagation(); setHover(null); setMenu({ account: a, x: Math.min(e.clientX, window.innerWidth - 215), y: Math.min(e.clientY, window.innerHeight - 280) }); };
    const showHover = (e: React.MouseEvent, a: Account) => { const r = e.currentTarget.getBoundingClientRect(); setHover({ account: a, left: Math.min(r.left, window.innerWidth - 284), top: r.bottom + 310 < window.innerHeight ? r.bottom + 8 : Math.max(8, r.top - 300) }); };
    return <div className="accounts-view"><div className="account-pools"><button className={pool === 'normal' ? 'active' : ''} onClick={() => reset(() => setPool('normal'))}>{tr("收集的账号")}<b>{data.pools?.normal ?? '…'}</b></button><button className={pool === 'suspended' ? 'active banned' : ''} onClick={() => reset(() => setPool('suspended'))}><ShieldAlert size={15}/>{tr("封禁池")}<b>{data.pools?.suspended || 0}</b></button><span />{pool === 'suspended' ? <button className="subtle" disabled={health.status === 'running'} onClick={() => check()}>{tr("检测是否解封")}</button> : <button className="subtle" onClick={() => { setValue(''); setAdding(true); }}><Plus size={15}/>{tr("添加账号")}</button>}</div>
 <div className="collection-strip"><button className={!collection ? 'active' : ''} onClick={() => reset(() => setCollection(''))}>{tr("全部合集")}</button>{collections.map(c => <button className={collection === c.id ? 'active' : ''} key={c.id} draggable title={tr('拖动调整合集顺序')} onDragStart={()=>{draggedCollection.current=c.id}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();reorderCollection(c.id)}} onClick={() => reset(() => setCollection(c.id))} onContextMenu={e => { e.preventDefault(); setValue(c.name); setRename(c); }}><Folder size={13}/>{c.name}<small>{pool === 'suspended' ? (c.suspended || 0) : c.count - (c.suspended || 0)}</small></button>)}<button className={collection === 'unfiled' ? 'active' : ''} onClick={() => reset(() => setCollection('unfiled'))}>{tr("未加入合集")}</button><button title={tr("新建账号合集")} onClick={() => { setValue(''); setNewCollection(true); }}><Plus size={15}/></button></div>
 <div className="accounts-filters"><input aria-label={tr("搜索收集的账号")} placeholder={tr("搜索昵称、备注、账号…")} value={query} onChange={e => { setQuery(e.target.value); setPage(1); setSelected([]); setHover(null); setLoading(true); }}/><RatingFilter value={rating} onChange={v => reset(() => setRating(v))}/><select aria-label={tr("账号排序")} value={sort} onChange={e => reset(() => setSort(e.target.value))}><option value="name">{tr("按名字")}</option><option value="new">{tr("最近添加")}</option><option value="checked">{tr("最近检查")}</option><option value="count">{tr("在库数量")}</option><option value="rating">{tr("评分优先")}</option></select><label className="stale-filter"><input type="checkbox" checked={stale} onChange={e => reset(() => setStale(e.target.checked))}/>{tr("七天未检查")}</label><label className="page-size">{tr("每页")}<select aria-label={tr("账号每页数量")} value={size} onChange={e => reset(() => setSize(+e.target.value))}>{[32, 64, 96, 128].map(n => <option key={n}>{n}</option>)}</select></label><button className="text-button" onClick={changed}>{tr("刷新")}</button></div>
 {pool === 'suspended' && <p className="hint">{tr("明确封禁的账号暂停参与更新，合集和照片都保留。检测恢复后返回普通账号区；原来被阻断的任务保留为暂停，可在采集任务中恢复。")}</p>}
 {health.status === 'running' && <div className="notice">{tr("正在检测")}{health.checked} / {health.total} · {health.current}{tr("· 恢复")}{health.restored}</div>}{health.status === 'completed' && health.total > 0 && <div className="notice">{tr("检测完成：恢复")}{health.restored}{tr("· 仍封禁")}{health.suspended}{tr("· 待检查")}{health.errors?.length || 0}</div>}
 <div className="accounts-selection"><small>{data.total}{tr("个账号 · 拖动框选，Ctrl 多选 · 右键头像管理")}</small><button onClick={() => setSelected([...new Set([...selected, ...data.items.map((a: Account) => a.id)])])}>{tr("选择本页")}</button><button onClick={() => run(async () => { const ids = await api<string[]>('accountIds', filters); if (confirm(tr("选择全部筛选结果，共 {0} 个账号？", [ids.length])))
        setSelected(ids); })}>{tr("选择全部结果")}</button><button title={tr("撤销最近一次资料编辑")} onClick={() => run(async () => { await api('undo'); changed(); })}><Undo2 size={13}/></button>{selected.length > 0 && <><b>{tr("已选")}{selected.length}</b><button onClick={() => setSelected([])}>{tr("取消")}</button>{pool !== 'suspended' && <button onClick={() => batch('collect')}>{tr("更新所选")}</button>}<select aria-label={tr("加入账号合集")} value="" onChange={e => { if (e.target.value)
        run(async () => { await api('collectionAction', { action: 'add', id: e.target.value, ids: selected }); changed(); }); }}><option value="">{tr("加入合集…")}</option>{collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>{collection && collection !== 'unfiled' && <button onClick={() => run(async () => { await api('collectionAction', { action: 'remove', id: collection, ids: selected }); changed(); })}>{tr("移出此合集")}</button>}<select aria-label={tr("批量账号评分")} value="" onChange={e => { if (e.target.value !== '')
        batch('rating', { rating: +e.target.value }); }}><option value="">{tr("修改评分…")}</option><option value="0">{tr("取消评分")}</option>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}{tr("星")}</option>)}</select><button onClick={() => check(selected)}>{tr("检测所选")}</button></>}</div>
 {message && <p className="hint" role="status">{message}</p>}{error && <div className="error-banner">{error}<button onClick={changed}>{tr("重试")}</button></div>}
 {loading ? <div className="account-card-grid">{Array.from({ length: 12 }, (_, i) => <div className="account-skeleton" key={i}/>)}</div> : data.items.length ? <div className="account-card-grid" ref={marquee.root} {...marquee.props}>{data.items.map((a: Account) => <article key={a.id} data-select-id={a.id} className={'account-card ' + (selected.includes(a.id) ? 'selected' : '')} onClick={e => { if (e.shiftKey && lastSelected.current) {
        const first = data.items.findIndex((v: Account) => v.id === lastSelected.current), last = data.items.findIndex((v: Account) => v.id === a.id);
        if (first >= 0) {
            setSelected([...new Set([...selected, ...data.items.slice(Math.min(first, last), Math.max(first, last) + 1).map((v: Account) => v.id)])]);
            return;
        }
    } if (e.shiftKey) {
        setSelected([...new Set([...selected, a.id])]);
        lastSelected.current = a.id;
        return;
    } if (e.ctrlKey || e.metaKey) {
        setSelected(selected.includes(a.id) ? selected.filter(id => id !== a.id) : [...selected, a.id]);
        lastSelected.current = a.id;
        return;
    } open(a); }} onContextMenu={e => context(e, a)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' && e.target === e.currentTarget)
        open(a); }}><div className="account-card-top"><div className="account-card-avatar" onMouseEnter={e => showHover(e, a)} onMouseLeave={() => setHover(null)} onFocus={e => showHover(e as any, a)} onBlur={() => setHover(null)}><Avatar account={a}/></div><div className="account-card-name"><strong title={a.alias || a.name || a.handle}>{a.alias || a.name || a.handle}</strong><span>@{a.handle}</span></div><div className="account-card-selection"><CountryBadge account={a} onClick={()=>setEditor(a)}/><input className="account-card-select" type="checkbox" aria-label={tr("选择账号 @") + a.handle} checked={selected.includes(a.id)} onClick={e => e.stopPropagation()} onChange={e => { setSelected(e.target.checked ? [...new Set([...selected, a.id])] : selected.filter(id => id !== a.id)); lastSelected.current = a.id; }}/></div></div><div className="account-card-meta"><div className="account-card-rating"><button title={tr("修改评分")} onClick={e => { e.stopPropagation(); setEditor(a); }}>{a.rating ? <><span>{'★'.repeat(a.rating)}</span><i>{'★'.repeat(5 - a.rating)}</i></> : <small>{tr("未评分")}</small>}</button></div><div className="account-card-collections">{a.categories.split(',').filter(Boolean).slice(0, 2).map(t => <span key={t}>{t}</span>)}{!a.categories && <small>{tr("未加入合集")}</small>}{a.categories.split(',').filter(Boolean).length > 2 && <small>+{a.categories.split(',').length - 2}</small>}</div></div><div className="account-card-bottom"><div className="account-media-counts"><button title={tr("图片 ") + (a.images || 0)} aria-label={tr("查看 @") + a.handle + tr(" 的图片")} onClick={e => { e.stopPropagation(); open(a, 'image'); }}><Images size={13}/>{(a.images || 0).toLocaleString()}</button><button title={tr("视频 ") + (a.videos || 0)} aria-label={tr("查看 @") + a.handle + tr(" 的视频")} onClick={e => { e.stopPropagation(); open(a, 'video'); }}><Film size={13}/>{(a.videos || 0).toLocaleString()}</button><button title={tr("其他媒体：GIF ") + (a.gifs || 0)} onClick={e => { e.stopPropagation(); open(a, 'gif'); }}>{tr("其他")}{(a.gifs || 0).toLocaleString()}</button></div><small title={a.availability === 'suspended' ? tr("平台明确返回封禁") : a.protected ? tr("此账号为私密账号，需使用获准关注的登录身份") : date(a.last_checked)}>{a.availability === 'suspended' ? tr("封禁") : a.task_status === 'running' ? tr("采集中") : a.protected ? tr("私密") : ago(a.last_checked)}</small><button aria-label={tr("管理 @") + a.handle} className="card-more" onClick={e => context(e, a)}><MoreHorizontal size={16}/></button></div></article>)}{marquee.overlay}</div> : <Empty title={pool === 'suspended' ? tr("封禁池为空") : tr("没有匹配的账号")} text={pool === 'suspended' ? tr("正常账号继续保留在普通账号区。") : tr("添加账号，或调整合集、评分和搜索条件。")}/>}
 <Pagination page={data.page} pages={data.pages} change={setPage}/>
 {hover && createPortal(<div className="avatar-popover" role="tooltip" style={{ left: hover.left, top: hover.top }}><strong>{hover.account.alias || hover.account.name || hover.account.handle}</strong><div><span>{tr("照片 / 视频 / GIF")}</span><b>{hover.account.images || 0} / {hover.account.videos || 0} / {hover.account.gifs || 0}</b></div><div><span>{tr("最近检查")}</span><b>{hover.account.last_checked ? date(hover.account.last_checked) : tr("尚未采集")}</b></div><div><span>{tr("最新媒体发布")}</span><b>{hover.account.last_published ? date(hover.account.last_published) : tr("尚未观察到")}</b></div><div><span>{tr("最近成功采集")}</span><b>{hover.account.last_success ? date(hover.account.last_success) : tr("尚无完整记录")}</b></div><div><span>{tr("本批新增 · 占用")}</span><b>+{hover.account.last_imported || 0} · {bytes(hover.account.storage || 0)}</b></div>{hover.account.note && <p>{hover.account.note}</p>}</div>, document.body)}
 {menu && createPortal(<div className="account-context-menu" style={{ left: menu.x, top: menu.y }} onClick={e => e.stopPropagation()}><strong>@{menu.account.handle}</strong>{[[tr("打开图库"), () => open(menu.account)], [tr("修改资料 / 评分 / 合集"), () => setEditor(menu.account)], [tr("曾用名与头像"), () => setHistory(menu.account)], [tr("查看采集任务"), () => openTasks(menu.account.id)], [tr("检查账号状态"), () => check([menu.account.id])], ...(pool === 'suspended' ? [] : [[tr("选择性采集"), () => collect('@' + menu.account.handle, 'preview')]])].map(([label, action]: any) => <button key={label} onClick={() => { action(); setMenu(null); }}>{label}</button>)}</div>, document.body)}
 {editor && <AccountEditor account={editor} collections={collections} close={() => setEditor(null)} run={run} changed={changed}/>}{history && <AccountHistory account={history} close={() => setHistory(null)}/>}
 {(adding || newCollection || rename) && <Modal title={adding ? tr("添加收集账号") : rename ? tr("重命名账号合集") : tr("新建账号合集")} close={() => { setAdding(false); setNewCollection(false); setRename(null); }}><label>{adding ? tr("账号或链接") : tr("合集名称")}<input autoFocus value={value} onChange={e => setValue(e.target.value)}/></label>{!adding && <p className="hint">{tr("一个账号可以加入多个合集，原照片与采集进度保持关联。右键合集可改名。")}</p>}<div className="modal-footer"><button className="primary" disabled={!value.trim()} onClick={() => run(async () => { if (adding)
        await api('addAccount', { value });
    else
        await api('collectionAction', rename ? { action: 'rename', id: rename.id, name: value } : { action: 'create', name: value }); setAdding(false); setNewCollection(false); setRename(null); changed(); })}>{tr("保存")}</button></div></Modal>}
 </div>;
}
