import 'flag-icons/css/flag-icons.min.css';
import { tr } from './i18n';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Images, Clock, Heart, Inbox, Download, Users, Tags, Trash2, Plus, Search, SlidersHorizontal, PanelRight, Moon, Sun, FolderOpen, ArrowUpRight, X, ChevronLeft, ChevronRight, Play, Check, Upload, Settings, Film, Sparkles, Undo2, CheckCheck, Copy, Folder, RefreshCw } from 'lucide-react';
import { api, Photo, Stats, Filters, Task, Account, date, bytes, duration } from './api';
import { Picture, Empty, Modal, CollectDialog, AccountHeader, RatingFilter, DetailPanel, Pagination, SettingsView } from './components';
import { TasksQueue, CompletionBanner } from './management';
import './style.css';
import './upgrade.css';
import './viewer.css';
import './redesign.css';
import { AccountsCards } from './accounts';
import { Dashboard } from './dashboard';
import { SimilarView } from './similar';
import { useMarquee } from './marquee';
import { useStored } from './controls';
import { readStored, writeStored, setWorkspaceScope } from './persistence';
import { WorkspaceButton } from './workspace';
import { BackgroundWork } from './background';
import { LibrarySwitch } from './library-switch';
import './focus.css';
import { ArrowLeft, House, Minus } from 'lucide-react';
const initialStats: Stats = { root: '', total: 0, trash: 0, revision: 0, tags: [], accountCategories: [], albums: [], pending: 0, bytes: 0, analysis: {}, active: null };
const labels: Record<string, string> = { home: tr("总览"), all: tr("全部媒体"), image: tr("照片"), video: tr("视频"), gif: tr("GIF 动图"), recent: tr("最近添加"), favorite: tr("个人收藏"), inbox: tr("待整理"), tasks: tr("采集任务"), accounts: tr("收集的账号"), similar: tr("相似图片"), settings: tr("设置"), trash: tr("回收站"), album: tr("我的相册") };
function App({ workspace }: {
    workspace: any;
}) {
    const [view, setView] = useState(() => readStored('last-view', 'accounts')), [stats, setStats] = useState<Stats>(initialStats), [items, setItems] = useState<Photo[]>([]), [total, setTotal] = useState(0), [pages, setPages] = useState(1), [page, setPage] = useState(1), [selected, setSelected] = useState<string[]>([]), [query, setQuery] = useState(''), [search, setSearch] = useState(''), [filter, setFilter] = useState<Filters>({ sort: 'new' }), [showFilters, setShowFilters] = useState(false), [account, setAccount] = useState<Account | null>(null), [album, setAlbum] = useState(''), [batch, setBatch] = useState(''), [detail, setDetail] = useState(() => readStored('detail-panel', false)), [zoom, setZoom] = useState(readStored('grid-size', 210)), [collect, setCollect] = useState<string | null>(null), [toast, setToast] = useState(workspace.networkWarning || ''), [error, setError] = useState(''), [busy, setBusy] = useState(0), [revision, setRevision] = useState(0), [loadedRevision, setLoadedRevision] = useState(0), [loadedTotal, setLoadedTotal] = useState(0), [full, setFull] = useState<Photo | null>(null), [scale, setScale] = useState(0), [semantic, setSemantic] = useState(false), [imageSearch, setImageSearch] = useState(''), [newAlbum, setNewAlbum] = useState(false), [albumName, setAlbumName] = useState(''), [addToAlbum, setAddToAlbum] = useState(false), [groups, setGroups] = useState<string[][]>([]), [compare, setCompare] = useState<string[] | null>(null);
    const [bootstrapped, setBootstrapped] = useState(false), [saveView, setSaveView] = useState(false), [viewName, setViewName] = useState('');
    useEffect(() => writeStored('last-view', view), [view]);
    useEffect(() => writeStored('detail-panel', detail), [detail]);
    const [gallerySize, setGallerySize] = useStored('gallery-page-size', 60), [history, setHistory] = useState<any[]>([]), [accountPool, setAccountPool] = useState('normal'), [accountStale, setAccountStale] = useState(false);
    const restoring = useRef(false), scrollRestore = useRef<number | null>(null);
    const marquee = useMarquee(selected, setSelected);
    const [collectMode, setCollectMode] = useState('latest'), [taskAccount, setTaskAccount] = useState('');
    const lastSelected = useRef(''), refreshPending = useRef(false), sidebarViews = ['home', 'tasks', 'accounts', 'similar', 'settings'];
    const isGallery = !sidebarViews.includes(view) || !!account;
    const filters: Filters = { ...filter, view: ['recent', 'favorite', 'inbox', 'trash'].includes(view) ? view : 'all', kind: ['image', 'video', 'gif'].includes(view) ? view : filter.kind, account: account?.id, album: album || undefined, batch: batch || undefined, q: semantic ? '' : search, ...(compare ? { ids: compare } : {}) };
    const filterKey = JSON.stringify(filters);
    const notify = (text: string) => setToast(text);
    const run = async (f: () => Promise<any>) => { setBusy(n => n + 1); try {
        return await f();
    }
    catch (e) {
        notify(e instanceof Error ? e.message : String(e));
    }
    finally {
        setBusy(n => Math.max(0, n - 1));
    } };
    const load = useCallback(async () => {
        const f: Filters = JSON.parse(filterKey);
        const r = (semantic && search) || imageSearch ? await api('aiSearch', { text: search, photo: imageSearch || undefined, filters: f, limit: 120 }) : await api('list', { ...f, page, limit: gallerySize });
        setItems(r.items);
        setTotal(r.total);
        setPages((semantic && search) || imageSearch ? 1 : r.pages);
        setLoadedRevision(r.revision ?? 0);
        setLoadedTotal(n => Math.max(n, stats.total));
    }, [filterKey, page, semantic, search, imageSearch, gallerySize]);
    const changed = () => { setRevision(n => n + 1); refreshPending.current = true; };
    useEffect(() => { const bridge = window.luma as any; return bridge?.onAssistantChanged?.(changed); }, []);
    useEffect(() => { const timer = setTimeout(() => setSearch(query), 350); return () => clearTimeout(timer); }, [query]);
    useEffect(() => { if (restoring.current)
        return; setPage(1); setSelected([]); lastSelected.current = ''; }, [filterKey, semantic]);
    useEffect(() => { if (!isGallery || !window.luma)
        return; let live = true; setBusy(n => n + 1); const f: Filters = JSON.parse(filterKey); const request = (semantic && search) || imageSearch ? api('aiSearch', { text: search, photo: imageSearch || undefined, filters: f, limit: 120 }) : api('list', { ...f, page, limit: gallerySize }); request.then(r => { if (live) {
        setItems(r.items);
        setTotal(r.total);
        setPages((semantic && search) || imageSearch ? 1 : r.pages);
        setLoadedRevision(r.revision ?? 0);
        setLoadedTotal(n => Math.max(n, stats.total));
    } }).catch(e => live && setError(e.message)).finally(() => setBusy(n => Math.max(0, n - 1))); return () => { live = false; }; }, [filterKey, page, revision, isGallery, semantic, search, imageSearch, gallerySize]);
    useEffect(() => { if (!window.luma)
        return; let stopped = false, running = false; const poll = async () => { if (running)
        return; running = true; try {
        const s = await api<Stats>('stats');
        if (stopped)
            return;
        setStats(s);
        setBootstrapped(true);
        setLoadedTotal(n => n || s.total);
        setError(s.offline || '');
        if (refreshPending.current) {
            refreshPending.current = false;
        }
    }
    catch (e) {
        if (!stopped)
            setError(e instanceof Error ? e.message : String(e));
    }
    finally {
        running = false;
    } }; poll(); const timer = setInterval(poll, 3000); return () => { stopped = true; clearInterval(timer); }; }, []);
    useEffect(() => { if (isGallery && items.length === 0 && stats.total > 0 && total === 0 && !search && !filter.textFilter)
        load().catch(() => { }); }, [stats.total]);
    useEffect(() => { const apply = (p: any) => { document.documentElement.dataset.theme = p.theme || localStorage.getItem('theme') || 'light'; document.documentElement.style.setProperty('--font-scale', String(p.fontScale || 1)); }; api('desktopSettings').then(apply).catch(() => apply({})); const bridge = window.luma as any; return bridge?.onPreferences?.(apply); }, []);
    useEffect(() => { if (toast) {
        const timer = setTimeout(() => setToast(''), 6500);
        return () => clearTimeout(timer);
    } }, [toast]);
    const remember = () => setHistory(h => [...h.slice(-39), { view, account, album, batch, filter, page, query, search, semantic, imageSearch, selected, compare, taskAccount, accountPool, accountStale, scroll: document.querySelector('.library')?.scrollTop || 0 }]);
    const navigate = (v: string) => { remember(); setTaskAccount(''); setView(v); setAccount(null); setAlbum(''); setBatch(''); setFilter({ sort: 'new' }); setQuery(''); setSemantic(false); setImageSearch(''); setSelected([]); setCompare(null); setPage(1); document.querySelector('.library')?.scrollTo(0, 0); };
    const goBack = () => { if (full) {
        setFull(null);
        return;
    } const previous = history[history.length - 1]; if (!previous)
        return; restoring.current = true; setHistory(h => h.slice(0, -1)); setView(previous.view); setAccount(previous.account); setAlbum(previous.album); setBatch(previous.batch); setFilter(previous.filter); setPage(previous.page); setQuery(previous.query); setSearch(previous.search); setSemantic(previous.semantic); setImageSearch(previous.imageSearch); setSelected(previous.selected); setCompare(previous.compare); setTaskAccount(previous.taskAccount); setAccountPool(previous.accountPool || 'normal'); setAccountStale(!!previous.accountStale); scrollRestore.current = previous.scroll; setTimeout(() => restoring.current = false, 0); };
    useEffect(() => { if (scrollRestore.current === null)
        return; let frame: number, n = 0; const restore = () => { const el = document.querySelector('.library'); if (!el)
        return; const top = scrollRestore.current; if (top === null)
        return; if (el.scrollHeight - el.clientHeight >= top || ++n > 120) {
        el.scrollTop = top;
        scrollRestore.current = null;
        return;
    } frame = requestAnimationFrame(restore); }; frame = requestAnimationFrame(restore); return () => cancelAnimationFrame(frame); }, [view, account, items.length]);
    useEffect(() => { const keys = (e: KeyboardEvent) => { if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        goBack();
    } }; const mouse = (e: MouseEvent) => { if (e.button === 3) {
        e.preventDefault();
        goBack();
    } }; window.addEventListener('keydown', keys); window.addEventListener('mouseup', mouse); return () => { window.removeEventListener('keydown', keys); window.removeEventListener('mouseup', mouse); }; }, [history, full]);
    const showAccounts = (pool: string, stale = false) => { setAccountPool(pool); setAccountStale(stale); navigate('accounts'); };
    const comparePhotos = (ids: string[]) => { remember(); setCompare(ids); setView('all'); setFilter({ sort: 'new' }); setSelected([]); setPage(1); };
    const pick = (p: Photo, e: React.MouseEvent) => {
        if (e.shiftKey && lastSelected.current) {
            const a = items.findIndex(i => i.id === lastSelected.current), b = items.findIndex(i => i.id === p.id);
            if (a >= 0) {
                setSelected([...new Set([...selected, ...items.slice(Math.min(a, b), Math.max(a, b) + 1).map(i => i.id)])]);
                return;
            }
        }
        if (e.shiftKey) {
            setSelected([...new Set([...selected, p.id])]);
            lastSelected.current = p.id;
            return;
        }
        setSelected(e.ctrlKey || e.metaKey ? (selected.includes(p.id) ? selected.filter(id => id !== p.id) : [...selected, p.id]) : [p.id]);
        lastSelected.current = p.id;
    };
    useEffect(()=>{const bridge=window.luma as any;return bridge?.onOpenAccount?.((value:any)=>{run(async()=>{const next=await api<Account>('account',{id:value.id});navigate('accounts');setAccount(next);setFilter({sort:'published'});setPage(1);setSelected([])})})},[navigate]);
    const context = (p: Photo, e: React.MouseEvent) => { e.preventDefault(); const ids = selected.includes(p.id) ? selected : [p.id]; setSelected(ids); run(async () => { const result = await api('contextMenu', { id: p.id, ids }); if (result)
        notify(result); }); };
    const update = (values: any, ids = selected) => run(async () => { await api('update', { ids, ...values }); changed(); });
    const remove = () => { if (!selected.length)
        return; if (confirm(tr("从整个资料库{0} {1} 项？{2}", [view === 'trash' ? tr("恢复") : tr("删除"), selected.length, view === 'trash' ? '' : tr("所有账号和相册视图都会受影响。图片先进入回收站，删除记录会阻止再次下载。")])))
        update({ trash: view === 'trash' ? 0 : 1 }).then(() => setSelected([])); };
    const importLocal = (folder = false) => run(async () => { const r = await api(folder ? 'folderDialog' : 'importDialog'); if (r) {
        notify(tr("新增 {0} · 重复 {1} · 已删排除 {2} · 失败 {3}", [r.added, r.duplicates, r.excluded, r.failed]));
        changed();
    } });
    const move = (direction: number) => { if (!full)
        return; const i = items.findIndex(p => p.id === full.id), next = items[i + direction]; if (next) {
        setFull(next);
        setScale(0);
    } };
    useEffect(() => { const key = (e: KeyboardEvent) => { if ((e.target as HTMLElement).matches('input,textarea,select'))
        return; if (e.key === 'Escape') {
        setFull(null);
        setCollect(null);
    } if (full && e.key === 'ArrowRight')
        move(1); if (full && e.key === 'ArrowLeft')
        move(-1); if (!full && e.code === 'Space' && selected.length) {
        e.preventDefault();
        const p = items.find(p => p.id === selected[0]);
        if (p) {
            setFull(p);
            setScale(0);
        }
    } if (!full && e.key === 'Delete')
        remove(); if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && isGallery) {
        e.preventDefault();
        setSelected([...new Set([...selected, ...items.map(p => p.id)])]);
    } }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key); }, [full, items, selected, isGallery, view]);
    return <div className="app-shell" data-theme-slot="window"><aside className="sidebar" data-theme-slot="sidebar"><WorkspaceButton initial={workspace} run={run}/><div className="side-label">{tr("采集与整理")}</div>{[{ id: 'accounts', icon: Users }, { id: 'tasks', icon: Download }, { id: 'similar', icon: Copy }].map(({ id, icon: Icon }) => <button key={id} className={'nav ' + (view === id && !account ? 'active' : '')} onClick={() => navigate(id)}><Icon size={17}/>{labels[id]}{id === 'tasks' && stats.active && <i className="dot"/>}</button>)}<button className={'nav ' + (semantic ? 'active' : '')} onClick={() => { navigate('all'); if (stats.analysis?.modelReady)
        setSemantic(true);
    else
        notify(tr("可先搜索推文与备注；本地语义模型可在设置中安装")); }}><Sparkles size={17}/>{tr("智能找图")}</button>
 <div className="side-label section-gap">{tr("资料库")}</div>{[{ id: 'favorite', icon: Heart }, { id: 'recent', icon: Clock }, { id: 'inbox', icon: Inbox }].map(({ id, icon: Icon }) => <button key={id} className={'nav ' + (view === id && !account ? 'active' : '')} onClick={() => navigate(id)}><Icon size={17}/>{labels[id]}</button>)}<details className="library-extra"><summary>{tr("更多媒体")}</summary>{[{ id: 'all', icon: Images }, { id: 'video', icon: Film }, { id: 'gif', icon: Play }, { id: 'trash', icon: Trash2 }].map(({ id, icon: Icon }) => <button key={id} className={'nav ' + (view === id && !account ? 'active' : '')} onClick={() => navigate(id)}><Icon size={16}/>{id === 'gif' ? tr("其他 · GIF") : labels[id]}{id === 'all' && <span>{bootstrapped ? stats.total : '…'}</span>}</button>)}</details>
 {(stats.savedViews?.length || 0) > 0 && <><div className="side-label section-gap">{tr("快捷视图")}</div><div className="side-views">{stats.savedViews?.map((v: any) => <div key={v.id}><button title={v.name} onClick={() => run(async () => { const q = v.query, f = q.filters || {}; navigate(f.view || 'all'); if (f.account)
        setAccount(await api('account', { id: f.account })); setAlbum(f.album || ''); setBatch(f.batch || ''); setFilter(f); setQuery(q.text || f.q || ''); setSearch(q.text || f.q || ''); setSemantic(!!q.semantic); })}><SlidersHorizontal size={14}/>{v.name}</button><button aria-label={tr("删除快捷视图 ") + v.name} onClick={() => run(async () => { if (confirm(tr("移除快捷视图“") + v.name + tr("”？照片和筛选中的账号不受影响。"))) {
        await api('deleteView', { id: v.id });
        changed();
    } })}><X size={12}/></button></div>)}</div></>}
 <div className="side-label section-gap">{tr("相册")}<button className="tiny" onClick={() => setNewAlbum(true)}><Plus size={13}/></button></div><div className="side-albums">{stats.albums.map(a => <button key={a.id} className={'nav ' + (album === a.id ? 'active' : '')} onClick={() => { navigate('album'); setAlbum(a.id); }}><Folder size={15}/>{a.name}<span>{a.count}</span></button>)}{!stats.albums.length && <p>{tr("按主题收集素材")}</p>}</div><div className="sidebar-bottom"><button className={'nav ' + (view === 'home' ? 'active' : '')} onClick={() => navigate('home')}><House size={17}/>{tr("总览")}</button><div className="local-badge" title={stats.root}><i className={'dot ' + (stats.offline ? 'red' : '')}/>{stats.offline ? tr("资料库离线") : tr("本地资料库")}<span>{bytes(stats.bytes)}</span></div><button className={'nav ' + (view === 'settings' ? 'active' : '')} onClick={() => navigate('settings')}><Settings size={17}/>{tr("设置")}</button></div></aside>
 <main><header className="toolbar"><button className="icon back-button" aria-label={tr("返回上一页")} title={tr("返回（Alt + ←）")} disabled={!history.length && !full} onClick={goBack}><ArrowLeft size={19}/></button><div className="breadcrumb"><strong>{account ? account.alias || '@' + account.handle : labels[view]}</strong></div><div className="toolbar-actions"><button className="icon" title={tr("最小化")} aria-label={tr("最小化")} onClick={() => run(() => api('windowMinimize'))}><Minus size={17}/></button>{isGallery && <label className="search"><Search size={16}/><input placeholder={semantic ? tr("描述你要找的照片…") : tr("搜索推文、备注、标签…")} value={query} onChange={e => setQuery(e.target.value)}/></label>}<button className={'icon ' + (semantic ? 'accent' : '')} title={tr("本地 AI 语义搜索")} onClick={() => { if (!stats.analysis?.modelReady) {
        notify(tr("请先到设置中安装本地中文搜图模型并分析照片"));
        return;
    } if (!isGallery)
        navigate('all'); setSemantic(!semantic); }}><Sparkles size={18}/></button><button className="icon" title={tr("导入媒体")} onClick={() => importLocal()}><Upload size={18}/></button><button className="icon" title={tr("显示详情")} onClick={() => setDetail(!detail)}><PanelRight size={18}/></button><button className="primary" onClick={() => { setCollectMode('latest'); setCollect(''); }}><Plus size={16}/>{tr("添加采集")}</button></div></header>
 <div className="content-row"><section className={'library ' + (view === 'tasks' && !account ? 'management-library' : '')}>{isGallery && <div className="content-heading"><span>{compare ? tr("相似图片比较 · ") : ''}{total.toLocaleString()}{tr("个结果")}{account ? tr(" · 按最新发布优先") : ''}</span><div><button className="text-button" onClick={() => { setViewName(''); setSaveView(true); }}><Plus size={13}/>{tr("保存此筛选")}</button><button className="text-button" onClick={() => importLocal(true)}><FolderOpen size={14}/>{tr("导入文件夹")}</button></div></div>}
 {!window.luma && <div className="notice">{tr("界面预览模式。文件、采集和模型功能请在桌面程序使用。")}</div>}{error && <div className="error-banner" role="alert">{error}<button onClick={() => { changed(); load().catch(e => setError(e.message)); }}>{tr("重新检查")}</button></div>}
 {stats.queueWaitingLogin && (stats.queued || 0) > 0 && <div className="notice">{tr("已保留")}{stats.queued}{tr("个排队任务，正在等待 X 登录。")}<button onClick={() => run(() => api('login'))}>{tr("打开登录窗口")}</button><button onClick={() => run(async () => { const r = await api('refreshSession'); if (!r.loggedIn)
        notify(tr("尚未检测到登录，请完成登录后再检查")); changed(); })}>{tr("登录完成，继续队列")}</button></div>}
 {semantic && !imageSearch && <div className="notice">{tr("本地 AI 搜图 · 已索引")}{stats.analysis?.indexed || 0}{tr("张照片 · 待识别")}{stats.analysis?.pending || 0}{tr("张。搜索只覆盖已建立索引的照片。")}</div>}
 {view === 'home' ? <Dashboard stats={stats} run={run} navigate={navigate} collect={() => { setCollectMode('latest'); setCollect(''); }} accounts={showAccounts} changed={changed}/> : view === 'settings' ? <SettingsView stats={stats} run={run} changed={changed}/> : view === 'tasks' ? <TasksQueue key={taskAccount} refresh={stats.revision} run={run} changed={changed} initialAccount={taskAccount} openAccount={id => run(async () => { const a = await api<Account>('account', { id }); navigate('accounts'); setAccount(a); setFilter({ sort: 'published' }); })} openBatch={t => run(async () => { navigate(t.account ? 'accounts' : 'all'); if (t.account)
            setAccount(await api<Account>('account', { id: t.account })); setFilter({ sort: 'published' }); setBatch(t.id); })}/> : view === 'accounts' && !account ? <AccountsCards key={accountPool + accountStale} stats={stats} initialPool={accountPool} initialStale={accountStale} open={(a, kind, b) => { remember(); setAccount(a); setFilter({ sort: 'published', kind }); setBatch(b || ''); setPage(1); setSelected([]); document.querySelector('.library')?.scrollTo(0, 0); }} collect={(h, m) => { setCollectMode(m || 'latest'); setCollect(h); }} openTasks={id => { navigate('tasks'); setTaskAccount(id); }} run={run}/> : view === 'similar' && !compare ? <SimilarView run={run} changed={changed} compare={comparePhotos}/> : <>
 {account && <><button className="back-link" onClick={goBack}><ChevronLeft size={14}/>{tr("返回账号")}</button><AccountHeader id={account.id} onRemoved={()=>{navigate('accounts');changed()}} revision={stats.revision} run={run} collect={h => { setCollectMode('latest'); setCollect(h); }} batch={id => { setBatch(id); setPage(1); setSelected([]); }} changed={changed} openTasks={() => { navigate('tasks'); setTaskAccount(account.id); }}/></>}
 <div className="collection-controls"><div className="button-row"><button className={'subtle ' + (showFilters ? 'accent' : '')} onClick={() => setShowFilters(!showFilters)}><SlidersHorizontal size={14}/>{tr("筛选")}</button><button className="subtle" onClick={() => setSelected([...new Set([...selected, ...items.map(p => p.id)])])}><CheckCheck size={14}/>{tr("全选当前页")}</button><button className="text-button" onClick={() => run(async () => { const ids = (semantic && search) || imageSearch ? items.map(p => p.id) : await api<string[]>('selectIds', filters as any); if (confirm(tr("选择全部筛选结果，共 {0} 项？", [ids.length])))
            setSelected(ids); })}>{tr("选择全部结果")}</button></div><div className="controls-right"><select aria-label={tr("排序")} value={filter.sort || 'new'} onChange={e => setFilter({ ...filter, sort: e.target.value })}><option value="new">{tr("最近采集")}</option><option value="old">{tr("最早采集")}</option><option value="published">{tr("最新发布优先")}</option><option value="size">{tr("文件大小")}</option></select><label className="page-size">{tr("每页")}<select aria-label={tr("图库每页数量")} value={gallerySize} onChange={e => { setGallerySize(+e.target.value); setPage(1); setSelected([]); }}>{[30, 60, 120, 240].map(n => <option key={n}>{n}</option>)}</select></label><input aria-label={tr("缩略图大小")} type="range" min="140" max="330" value={zoom} onChange={e => { setZoom(+e.target.value); writeStored('grid-size', +e.target.value); }}/></div></div>
 {showFilters && <div className="filters-panel"><div className="filter-inline"><select value={filter.kind || ''} onChange={e => setFilter({ ...filter, kind: e.target.value })}><option value="">{tr("所有媒体类型")}</option><option value="image">{tr("照片")}</option><option value="video">{tr("视频")}</option><option value="gif">GIF</option></select><select value={filter.shape || ''} onChange={e => setFilter({ ...filter, shape: e.target.value })}><option value="">{tr("所有方向")}</option><option value="portrait">{tr("竖图")}</option><option value="landscape">{tr("横图")}</option><option value="square">{tr("近方形")}</option></select><select value={filter.accountCategory || ''} onChange={e => setFilter({ ...filter, accountCategory: e.target.value })}><option value="">{tr("所有账号合集")}</option>{stats.accountCategories.map(t => <option key={t}>{t}</option>)}</select><RatingFilter value={filter.accountRating || 'all'} onChange={v => setFilter({ ...filter, accountRating: v })}/><select value={filter.tag || ''} onChange={e => setFilter({ ...filter, tag: e.target.value })}><option value="">{tr("所有图片标签")}</option>{stats.tags.map(t => <option key={t}>{t}</option>)}</select><select value={filter.textFilter || ''} onChange={e => setFilter({ ...filter, textFilter: e.target.value })}><option value="">{tr("全部内容")}</option><option value="text">{tr("疑似文字图")}</option><option value="pending">{tr("待分析照片")}</option></select></div><div className="filter-inline"><select value={filter.dateField || 'created'} onChange={e => setFilter({ ...filter, dateField: e.target.value })}><option value="created">{tr("按采集日期")}</option><option value="published">{tr("按推文发布日期")}</option></select><input aria-label={tr("开始日期")} type="date" value={filter.from || ''} onChange={e => setFilter({ ...filter, from: e.target.value })}/><span>{tr("至")}</span><input aria-label={tr("结束日期")} type="date" value={filter.to || ''} onChange={e => setFilter({ ...filter, to: e.target.value })}/>{filter.textFilter === 'text' && <><span>{tr("文字图强度")}</span><select value={filter.textThreshold ?? .6} onChange={e => setFilter({ ...filter, textThreshold: +e.target.value })}><option value="0.4">{tr("宽松")}</option><option value="0.6">{tr("标准")}</option><option value="0.8">{tr("严格")}</option></select></>}<button className="text-button" onClick={() => { setFilter({ sort: 'new' }); setBatch(''); setCompare(null); setQuery(''); }}>{tr("清除筛选")}</button></div>{filter.textFilter === 'text' && <p className="hint">{tr("仅筛选供你选择，不自动删除。白底商品图需人工核对；还有")}{stats.pending}{tr("张照片待分析。")}</p>}</div>}
 {(batch || compare) && <div className="notice">{batch ? tr("正在查看一个采集批次") : tr("正在比较一个相似图片组")}<button onClick={() => { setBatch(''); setCompare(null); setSelected([]); }}>{tr("返回全部")}</button></div>}
 {stats.total > loadedTotal && <div className="new-items"><span>{tr("图库有更新，当前选择和浏览位置已保留。")}</span><button onClick={() => { setPage(1); changed(); }}>{tr("刷新查看")}</button></div>}
 {selected.length === 1 && items.find(p => p.id === selected[0])?.kind === 'image' && <button className="text-button" onClick={() => { if (!stats.analysis?.modelReady) {
            notify(tr("请先在设置中安装模型并完成索引"));
            return;
        } setImageSearch(selected[0]); setSemantic(true); setQuery(''); setPage(1); }}><Sparkles size={14}/>{tr("用所选照片找相似图")}</button>}
 {imageSearch && <div className="notice">{tr("正在按照片内容搜索，仅搜索已建立本地索引的照片。")}<button onClick={() => { setImageSearch(''); setSemantic(false); }}>{tr("结束以图找图")}</button></div>}
 {selected.length > 0 && <div className="selection-bar"><strong>{tr("已选 {0} 项", [selected.length])}</strong><button onClick={() => setSelected([])}>{tr("取消选择")}</button><button onClick={() => run(() => api('copyFiles', { ids: selected }))}><Copy size={14}/>{tr("复制文件")}</button><button onClick={() => setAddToAlbum(true)}><Folder size={14}/>{tr("加入相册")}</button>{album && <button onClick={() => run(async () => { await api('album', { action: 'remove', album, ids: selected }); changed(); setSelected([]); })}>{tr("从此相册移除")}</button>}<button onClick={() => update({ reviewed: 1 })}><Check size={14}/>{tr("标为已整理")}</button><button onClick={() => run(() => api('exportDialog', { ids: selected }))}>{tr("导出")}</button><button className="danger-text" onClick={remove}><Trash2 size={14}/>{view === 'trash' ? tr("恢复") : tr("删除")}</button>{view === 'trash' && <button className="danger-text" onClick={() => { if (confirm(tr("彻底删除所选 {0} 项文件？删除排除记录会保留，此操作不能撤销。", [selected.length])))
            run(async () => { await api('purge', { ids: selected }); setSelected([]); changed(); }); }}>{tr("彻底删除文件")}</button>}<button title={tr("撤销最近一次编辑")} onClick={() => run(async () => { await api('undo'); changed(); })}><Undo2 size={14}/></button></div>}
 {!bootstrapped ? <Empty title={tr("正在读取资料库…")} text={tr("正在连接已有资料库或整理旧数据，请稍候。")}/> : items.length ? <div className="photo-grid" ref={marquee.root} {...marquee.props} style={{ gridTemplateColumns: `repeat(auto-fill,minmax(${zoom}px,1fr))` }}>{items.map(p => <article className={'photo-card ' + (selected.includes(p.id) ? 'is-selected' : '')} tabIndex={0} key={p.id} data-select-id={p.id} onClick={e => pick(p, e)} onContextMenu={e => context(p, e)} onDoubleClick={() => { setFull(p); setScale(0); }} onKeyDown={e => { if (e.key === 'Enter')
            setSelected([p.id]); }}><div className="photo-wrap"><Picture photo={p}/><button className={'select-check ' + (selected.includes(p.id) ? 'checked' : '')} aria-label={tr("选择媒体")} onClick={e => { e.stopPropagation(); setSelected(selected.includes(p.id) ? selected.filter(id => id !== p.id) : [...selected, p.id]); }}><Check size={13}/></button>{p.kind !== 'image' && <span className="media-badge"><Play size={11}/>{p.kind === 'gif' ? 'GIF' : duration(p.duration)}</span>}<button className={'photo-heart ' + (p.favorite ? 'liked' : '')} title={tr("收藏")} onClick={e => { e.stopPropagation(); update({ favorite: p.favorite ? 0 : 1 }, [p.id]); }}><Heart size={15} fill={p.favorite ? 'currentColor' : 'none'}/></button></div><div className="photo-caption"><strong>{p.author ? '@' + p.author : tr("本地媒体")}{p.source_count > 1 && <small> · {p.source_count}{tr("来源")}</small>}</strong><span>{p.kind === 'image' ? `${p.width} × ${p.height}` : bytes(p.size)}</span></div><div className="chips">{p.tags.split(',').filter(Boolean).slice(0, 3).map(t => <small key={t}>{t}</small>)}{p.text_score !== null && p.text_score >= .6 && <small>{tr("疑似文字图")}</small>}{p.reviewed === 1 && <small>{tr("已整理")}</small>}</div><time className="photo-published" dateTime={p.published||undefined} title={p.published?tr('发布时间')+' · '+date(p.published):tr('未记录发布时间')}>{p.published?new Date(p.published).toLocaleDateString():tr('本地导入 / 发布时间未知')}</time></article>)}{marquee.overlay}</div> : <Empty title={stats.total ? tr("没有匹配的媒体") : tr("为灵感留一个位置")} text={stats.total ? tr("调整筛选条件，或先完成本地内容分析。") : tr("添加 X 账号或帖子链接，也可以导入电脑里的照片和视频。")}><button className="primary" onClick={() => { setCollectMode('latest'); setCollect(''); }}><Plus size={15}/>{tr("添加采集")}</button><button className="subtle" onClick={() => importLocal()}>{tr("导入本地媒体")}</button></Empty>}
 <Pagination page={page} pages={pages} change={setPage}/>
 </>}
 </section>{isGallery && detail && (selected.length ? <DetailPanel key={selected[0]} id={selected[0]} selected={selected} run={run} refresh={changed} close={() => setDetail(false)}/> : <aside className="inspector"><div className="inspector-title">{tr("媒体详情")}<button className="icon" onClick={() => setDetail(false)}><X size={15}/></button></div><div className="inspector-empty"><Images size={28}/><p>{tr("选择一项媒体")}</p><span>{tr("查看原帖、备注与文件信息")}<br />{tr("Ctrl 多选，Shift 连选")}<br />{tr("右键复制，空格预览")}</span></div></aside>)}</div><footer><BackgroundWork stats={stats} run={run}/><button className="footer-undo" disabled={view === 'similar'} title={tr("撤销最近一次照片、账号或相册编辑；相似图整理使用页面内的撤销")} aria-label={tr("撤销最近一次编辑")} onClick={() => run(async () => { await api('undo'); changed(); notify(tr("已撤销最近一次编辑")); })}><Undo2 size={14}/></button><span><i className={'dot ' + (error ? 'red' : '')}/>{error ? tr("需要检查后台连接") : !bootstrapped ? tr("正在读取资料库…") : stats.active ? tr("正在后台采集") : tr("本地资料库已就绪")}</span><span>{busy > 0 ? tr("正在处理…") : tr("{0} 项 · 本地保存", [stats.total])}<span className="footer-divider"/>v0.5.1-beta.1</span></footer></main>
 {collect !== null && <CollectDialog initial={collect} initialMode={collectMode} close={() => setCollect(null)} run={run} done={() => { navigate('tasks'); changed(); }}/>}
 {saveView && <Modal title={tr("保存快捷视图")} close={() => setSaveView(false)}><p className="hint">{tr("保存当前账号、合集、时间、类型和搜索条件。符合条件的新媒体会自动出现在视图中，原文件位置保持不变。")}</p><label>{tr("视图名称")}<input autoFocus aria-label={tr("快捷视图名称")} value={viewName} maxLength={60} onChange={e => setViewName(e.target.value)}/></label><div className="modal-footer"><button className="primary" disabled={!viewName.trim() || !!imageSearch || !!compare} onClick={() => run(async () => { await api('saveView', { name: viewName, query: { filters, semantic, text: search } }); setSaveView(false); changed(); notify(tr("已保存到侧栏快捷视图")); })}>{tr("保存视图")}</button></div>{(imageSearch || compare) && <p className="hint">{tr("请先结束以图找图或临时相似组比较，再保存动态筛选。")}</p>}</Modal>}
 {newAlbum && <Modal title={tr("创建相册")} close={() => setNewAlbum(false)}><label>{tr("相册名称")}<input autoFocus value={albumName} onChange={e => setAlbumName(e.target.value)} placeholder={tr("例如：鞋子参考")}/></label><div className="modal-footer"><button className="primary" disabled={!albumName.trim()} onClick={() => run(async () => { await api('album', { action: 'create', name: albumName }); setNewAlbum(false); setAlbumName(''); changed(); })}>{tr("创建")}</button></div></Modal>}
 {addToAlbum && <Modal title={tr("加入相册")} close={() => setAddToAlbum(false)}><p className="muted">{tr("为所选")}{selected.length}{tr("项建立相册关联，原文件只保留一份。")}</p><div className="album-choices">{stats.albums.map(a => <button key={a.id} onClick={() => run(async () => { await api('album', { action: 'add', album: a.id, ids: selected }); setAddToAlbum(false); changed(); })}><Folder size={17}/>{a.name}</button>)}</div>{!stats.albums.length && <button className="subtle" onClick={() => { setAddToAlbum(false); setNewAlbum(true); }}>{tr("先创建相册")}</button>}</Modal>}
 <CompletionBanner />
 {full && <div className="lightbox" role="dialog" aria-modal="true" aria-label={tr("媒体预览")}>
  <div className="viewer-toolbar"><span>{full.kind === 'video' ? tr("视频") : full.kind === 'gif' ? 'GIF' : tr("原图")} · {full.width} × {full.height}</span><div>{full.kind === 'image' && <><button onClick={() => setScale(0)} aria-pressed={!scale}>{tr("适应窗口")}</button><button onClick={() => setScale(1)} aria-pressed={scale === 1}>100%</button><input aria-label={tr("大图缩放")} type="range" min=".25" max="3" step=".05" value={scale || 1} onChange={e => setScale(+e.target.value)}/></>}<button title={tr("复制原图")} aria-label={tr("复制原图")} onClick={() => run(() => api('copyImage', { id: full.id }))}><Copy size={16}/></button><button title={tr("关闭预览（Esc）")} aria-label={tr("关闭预览")} onClick={() => setFull(null)}><X size={21}/></button></div></div>
  <div className="viewer-stage"><button className="viewer-prev" aria-label={tr("上一项")} disabled={items.findIndex(p => p.id === full.id) <= 0} onClick={() => move(-1)}><ChevronLeft size={27}/></button><div className={'viewer-content ' + (scale ? 'native-size' : '')} key={full.id}><div className="viewer-media">{(full.kind === 'video' || full.kind === 'gif' && full.format === 'mp4') ? <div className="video-viewer"><video src={'luma://media/' + full.id} controls preload="metadata"/><button className="subtle" onClick={() => run(() => api('openMedia', { id: full.id }))}>{tr("无法播放？使用系统播放器打开")}</button></div> : <img src={'luma://media/' + full.id} alt={tr("原始媒体")} style={scale ? { width: full.width * scale } : {}}/>}</div></div><button className="viewer-next" aria-label={tr("下一项")} disabled={items.findIndex(p => p.id === full.id) >= items.length - 1} onClick={() => move(1)}><ChevronRight size={27}/></button></div>
  <p className="viewer-caption">{full.author ? '@' + full.author : tr("本地媒体")} · {bytes(full.size)}{tr("· 左右方向键翻页 · Esc 关闭")}</p>
 </div>}
 {toast && <div className="toast" role="status">{toast}<button className="icon" onClick={() => setToast('')}><X size={14}/></button></div>}
 </div>;
}
function Bootstrap() { const [workspace, setWorkspace] = useState<any>(null), [error, setError] = useState(''); useEffect(() => { api('workspaceInfo').then(w => { setWorkspaceScope(w.current.id, w.items[0]?.id === w.current.id); setWorkspace(w); }).catch(e => setError(e.message)); }, []); return workspace ? <App workspace={workspace}/> : <div className="bootstrap"><Images size={30}/><p>{error || tr("正在连接原资料库，升级前会自动备份数据库…")}</p>{error && <button onClick={() => api('reloadWindow')}>{tr("重新连接")}</button>}</div>; }
createRoot(document.getElementById('root')!).render(<><Bootstrap /><LibrarySwitch /></>);
