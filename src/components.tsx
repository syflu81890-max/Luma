import {LanguageSetting,ProjectFeedback} from './language';
import {CollectionPicker,NoteShortcuts,CountrySelect,CountryBadge,AccountRemoval} from './account-fields';
import {AccountHistory} from './accounts';
import { tr } from './i18n';
import React, { useState, useEffect, useRef } from 'react';
import { Images, Play, X, Star, Download, Pause, Users, FolderOpen, ArrowUpRight, Clock, Check, Plus, Copy, Settings, ChevronLeft, ChevronRight, RefreshCw, Trash2 } from 'lucide-react';
import { LimitInput } from './controls';
import { AssistantSettings } from './assistant';
import { cachedMedia } from './media';
import { api, date, bytes, duration, statuses, Photo, Account, Task, Detail, Stats } from './api';
export function Picture({ photo }: {
    photo: Photo;
}) {
    const [src, setSrc] = useState(''), ref = useRef<HTMLDivElement>(null);
    useEffect(() => { let alive = true, loaded = false; const observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting) && !loaded) {
        loaded = true;
        cachedMedia('image', photo.id).then(s => alive && setSrc(s)).catch(() => { });
        observer.disconnect();
    } }, { rootMargin: '200px' }); if (ref.current)
        observer.observe(ref.current); return () => { alive = false; observer.disconnect(); }; }, [photo.id]);
    return <div className="picture" ref={ref} style={{ background: photo.color || 'var(--field)' }}>{src ? <img src={src} alt={photo.tags || tr("媒体预览")} draggable={false}/> : <Images size={23}/>}</div>;
}
export function Avatar({ account, revision = 0 }: {
    account: Account;
    revision?: number;
}) {
    const [src, setSrc] = useState(''), ref = useRef<HTMLDivElement>(null), identity=useRef(account.id), version = [revision, account.pinned_avatar||account.avatar_path, account.custom_avatar].join('|');
    useEffect(() => { let alive = true, timer: any, attempt = 0; if(identity.current!==account.id){setSrc('');identity.current=account.id} if (!account.pinned_avatar && !account.avatar_path && !account.custom_avatar && !account.avatar_url)
        return; const load = () => cachedMedia('avatar', account.id, version).then(s => { if (!alive)
        return; if(s)setSrc(s); if (!s && attempt++ < 3)
        timer = setTimeout(load, 1800); }).catch(() => { }); const observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) {
        observer.disconnect();
        load();
    } }, { rootMargin: '120px' }); if (ref.current)
        observer.observe(ref.current); return () => { alive = false; observer.disconnect(); clearTimeout(timer); }; }, [account.id, version]);
    return <div ref={ref} className="avatar">{src ? <img src={src} alt={tr("账号头像")} draggable={false}/> : <span>{(account.alias || account.name || account.handle)[0]?.toUpperCase()}</span>}</div>;
}
export function Modal({ title, children, close, wide = false }: {
    title: string;
    children: React.ReactNode;
    close: () => void;
    wide?: boolean;
}) { return <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget)
    close(); }}><section className={'modal ' + (wide ? 'wide' : '')} role="dialog" aria-modal="true" aria-label={title}><div className="modal-title"><h2>{title}</h2><button className="icon" onClick={close} aria-label={tr("关闭")}><X size={19}/></button></div>{children}</section></div>; }
export function Empty({ title, text, children }: {
    title: string;
    text: string;
    children?: React.ReactNode;
}) { return <div className="empty"><div className="empty-art"><Images size={36}/></div><h2>{title}</h2><p>{text}</p><div className="empty-actions">{children}</div></div>; }
type Run = (f: () => Promise<any>) => Promise<any>;
export function CollectDialog({ initial = '', initialMode = 'latest', close, run, done }: {
    initial?: string;
    initialMode?: string;
    close: () => void;
    run: Run;
    done: () => void;
}) {
    const [url, setUrl] = useState(initial), [limit, setLimit] = useState(0), [mode, setMode] = useState(initialMode), [from, setFrom] = useState(''), [to, setTo] = useState(''), [kinds, setKinds] = useState(['image', 'video', 'gif']), [retweets, setRetweets] = useState(false), [replies, setReplies] = useState(true), [logged, setLogged] = useState(false), [busy, setBusy] = useState(false);
    useEffect(() => { api('loginStatus').then(s => setLogged(s.loggedIn)).catch(() => { }); }, []);
    return <Modal title={tr("添加采集")} close={close}><p className="muted">{tr("原图、视频和 GIF 会保留推文来源。默认只检查新增内容。")}</p><label>{tr("账号或帖子链接")}<input autoFocus placeholder={tr("@username 或 https://x.com/…")} value={url} onChange={e => setUrl(e.target.value)}/></label><div className="form-row"><label>{tr("采集方式")}<select value={mode} onChange={e => setMode(e.target.value)}><option value="latest">{tr("抓取最新 / 继续补齐")}</option><option value="history">{tr("扫描历史（保留删除排除）")}</option><option value="preview">{tr("预览后勾选下载")}</option></select></label><label>{tr("本次数量上限")}<LimitInput value={limit} onChange={setLimit}/></label></div><div className="form-row"><label>{tr("发布时间从")}<input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label><label>{tr("到")}<input type="date" value={to} onChange={e => setTo(e.target.value)}/></label></div><div className="check-row">{[['image', tr("照片")], ['video', tr("视频")], ['gif', 'GIF']].map(([k, label]) => <label key={k}><input type="checkbox" checked={kinds.includes(k)} onChange={e => setKinds(e.target.checked ? [...kinds, k] : kinds.filter(i => i !== k))}/>{label}</label>)}</div><div className="check-row"><label><input type="checkbox" checked={retweets} onChange={e => setRetweets(e.target.checked)}/>{tr("包含转发")}</label><label><input type="checkbox" checked={replies} onChange={e => setReplies(e.target.checked)}/>{tr("包含回复")}</label></div><div className="notice">{logged ? tr("已检测到本地 X 登录会话") : tr("未检测到登录会话，建议先登录 X")}<button onClick={() => run(async () => { await api('login'); setLogged((await api('loginStatus')).loggedIn); })}>{tr("打开登录窗口")}</button><button onClick={() => run(async () => setLogged((await api('loginStatus')).loggedIn))}>{tr("刷新状态")}</button></div><p className="hint">{tr("不限数量会扫描到已有进度或可访问的末尾。预览候选按页展示。日期或类型筛选任务不会推进完整账号的更新边界。")}</p><div className="modal-footer"><button className="subtle" onClick={close}>{tr("取消")}</button><button className="primary" disabled={!url || !kinds.length || busy} onClick={() => { setBusy(true); run(async () => { await api('addTask', { url, limit, mode, options: { from, to, kinds, retweets, replies } }); close(); done(); }).finally(() => setBusy(false)); }}><Download size={16}/>{tr("开始")}</button></div></Modal>;
}
export function RatingFilter({ value, onChange }: {
    value: string;
    onChange: (s: string) => void;
}) { return <select aria-label={tr("账号评分筛选")} value={value} onChange={e => onChange(e.target.value)}><option value="all">{tr("所有账号评分")}</option><option value="unrated">{tr("未评分")}</option>{[5, 4, 3, 2, 1].map(n => <option key={n} value={n}>{n}{tr("星")}</option>)}<option value="4+">{tr("4 星及以上")}</option><option value="3+">{tr("3 星及以上")}</option></select>; }
export function AccountHeader({ id, revision, run, collect, batch, changed, openTasks,onRemoved }: {
    id: string;
    revision: number;
    run: Run;
    collect: (handle: string) => void;
    batch: (id: string) => void;
    changed: () => void;
    openTasks?: () => void;
    onRemoved?:()=>void;
}) {
    const [collections,setCollections]=useState<any[]>([]),[identities,setIdentities]=useState(false),[removing,setRemoving]=useState(false);
    useEffect(()=>{api<any[]>('collections').then(setCollections).catch(()=>{})},[]);
    const [account, setAccount] = useState<Account | null>(null), [editing, setEditing] = useState(false), [history, setHistory] = useState(false), [draft, setDraft] = useState<any>({}), [rule, setRule] = useState<any>({ enabled: false, type: 'interval', hours: 6, time: '09:00', limit: 0, onOpen: true, offset: -new Date().getTimezoneOffset() });
    const load = () => api<Account>('account', { id }).then(setAccount);
    useEffect(() => { load().catch(() => { }); }, [id, revision]);
    if (!account)
        return null;
    return <div className="account-detail"><div className="account-top"><Avatar account={account}/><div className="account-heading"><h2>{account.alias || account.name || account.handle}</h2><p><CountryBadge account={account} onClick={()=>{setDraft({...account});setEditing(true)}}/>@{account.handle} <span className="stars">{account.rating ? '★'.repeat(account.rating) : tr("未评分")}</span></p><div className="chips">{account.categories.split(',').filter(Boolean).map(t => <small key={t}>{t}</small>)}</div></div><button className="subtle" onClick={() => { setDraft({ ...account }); setEditing(true); }}>{tr("账号资料")}</button><button className="subtle" onClick={openTasks}><Clock size={15}/>{tr("采集任务")}</button><button className="subtle" onClick={()=>setIdentities(true)}>{tr('历史头像与昵称')}</button><button className="danger-text" onClick={()=>setRemoving(true)}>{tr('清空删除账号')}</button><button className="primary" onClick={() => collect('@' + account.handle)}><Download size={15}/>{tr("采集")}</button></div>{account.note && <p className="account-note">{account.note}</p>}<div className="account-metrics"><span>{tr("当前保留")}<b>{account.retained}</b>{tr("项")}</span><span>{tr("最近检查")}{date(account.last_checked)}</span><button onClick={() => setHistory(!history)}>{history ? tr("收起") : tr("展开")}{tr("采集记录")}</button></div>{history && <div className="batch-list">{account.tasks?.map(t => <button key={t.id} disabled={t.mode === 'legacy'} onClick={() => batch(t.id)}><span>{date(t.created)}</span><span>{statuses[t.status]}{tr("· 新增")}{t.imported}{tr("· 重复")}{t.duplicates}{tr("· 排除")}{t.excluded}</span><ArrowUpRight size={14}/></button>)}<div className="hint">{tr("旧版记录保留原统计；新版批次可精确查看关联媒体。")}</div></div>}
 {editing && <Modal title={tr("收集账号资料")} close={() => setEditing(false)}><div className="form-row"><label>{tr("私人别名")}<input value={draft.alias} onChange={e => setDraft({ ...draft, alias: e.target.value })}/></label><label>{tr("账号评分")}<select value={draft.rating} onChange={e => setDraft({ ...draft, rating: +e.target.value })}><option value="0">{tr("未评分")}</option>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{'★'.repeat(n)} · {n}{tr("星")}</option>)}</select></label></div><label>{tr('账号合集')}</label><CollectionPicker value={draft.categories||''} onChange={categories=>setDraft({...draft,categories})} collections={collections} onCollections={setCollections}/><CountrySelect account={draft} onChange={country=>setDraft({...draft,country})}/><p className="hint">{tr('别名用于显示和识别账号；备注记录内容特点和收藏理由。')}</p><label>{tr("账号备注")}<textarea value={draft.note} onChange={e => setDraft({ ...draft, note: e.target.value })}/></label><NoteShortcuts value={draft.note||''} onChange={note=>setDraft({...draft,note})}/><div className="button-row"><button className="subtle" onClick={() => run(async () => { await api('avatarDialog', { id }); changed(); await load(); })}>{tr("自定义头像")}</button><button className="subtle" onClick={() => run(async () => { await api('saveAccount', { id, custom_avatar: '' }); await api('refreshAvatar', { id }); changed(); await load(); })}>{tr("使用官方头像")}</button></div><div className="danger-zone"><p>{tr("重新扫描保留已删除排除记录；清除排除可能允许相关图片在其他账号下再次被收集。")}</p><button onClick={() => { if (confirm(tr("重置历史采集边界？已删除图片仍会跳过。")))
        run(async () => { await api('resetAccount', { id }); changed(); }); }}>{tr("重置采集边界")}</button><button onClick={() => { if (confirm(tr("允许重新收集该账号以前删除的内容？共享图片的全库排除记录也会被清除。")))
        run(async () => { await api('resetAccount', { id, clearExcluded: true }); changed(); }); }}>{tr("重置并清除删除排除")}</button></div><div className="modal-footer"><button className="primary" onClick={() => run(async () => { await api('saveAccount', draft); setEditing(false); changed(); await load(); })}>{tr("保存资料")}</button></div></Modal>}
 {identities&&<AccountHistory account={account} close={()=>setIdentities(false)}/>} {removing&&<AccountRemoval account={account} close={()=>setRemoving(false)} run={run} removed={()=>{changed();onRemoved?.()}}/>}
 </div>;
}
export function DetailPanel({ id, run, selected, refresh, close }: {
    id: string;
    run: Run;
    selected: string[];
    refresh: () => void;
    close: () => void;
}) {
    const [detail, setDetail] = useState<Detail | null>(null), [note, setNote] = useState(''), [tag, setTag] = useState(''), [mode, setMode] = useState('add'), [saved, setSaved] = useState('');
    useEffect(() => { let alive = true; api<Detail>('detail', { id }).then(d => { if (!alive)
        return; setDetail(d); setNote(localStorage.getItem('draft-note-' + id) ?? d.note); setTag(d.tags); }).catch(() => { }); return () => { alive = false; }; }, [id]);
    if (!detail)
        return null;
    return <aside className="inspector"><div className="inspector-title">{selected.length > 1 ? tr("已选 {0} 项", [selected.length]) : tr("媒体详情")}<button className="icon" onClick={close}><X size={15}/></button></div><div className="inspector-preview"><Picture photo={detail}/></div><h3>{detail.author ? '@' + detail.author : tr("本地导入")} <small>{detail.kind === 'video' ? tr("视频") : detail.kind === 'gif' ? 'GIF' : tr("照片")}</small></h3><dl><dt>{tr("分辨率")}</dt><dd>{detail.width} × {detail.height}</dd><dt>{tr("大小")}</dt><dd>{bytes(detail.size)}</dd>{detail.duration > 0 && <><dt>{tr("时长")}</dt><dd>{duration(detail.duration)}</dd></>}<dt>{tr("采集时间")}</dt><dd>{date(detail.created)}</dd></dl><div className="detail-section"><label>{tr("图片标签")}<select value={mode} onChange={e => setMode(e.target.value)}><option value="add">{tr("追加")}</option><option value="remove">{tr("移除")}</option><option value="replace">{tr("替换")}</option></select></label><textarea value={tag} onChange={e => setTag(e.target.value)}/><button className="subtle" onClick={() => run(async () => { await api('update', { ids: selected.length ? selected : [id], tags: tag, tagMode: mode }); setSaved(tr("标签已保存")); refresh(); })}>{tr("保存到所选媒体")}</button></div><div className="detail-section"><label>{tr("我的备注")}<small>{saved}</small></label><textarea value={note} onChange={e => { setNote(e.target.value); localStorage.setItem('draft-note-' + id, e.target.value); setSaved(tr("草稿已保留")); }}/><button className="subtle" onClick={() => run(async () => { if (selected.length > 1 && !confirm(tr("用这段备注替换 {0} 项的备注？", [selected.length])))
        return; await api('update', { ids: selected.length ? selected : [id], note }); localStorage.removeItem('draft-note-' + id); setSaved(tr("备注已保存")); refresh(); })}>{tr("保存备注")}</button></div><div className="detail-section"><label>{tr("原帖内容")}<small>{detail.sources.length}{tr("个来源")}</small></label>{detail.sources.length ? detail.sources.map(s => <article className="source" key={s.url}><strong>@{s.handle || tr("来源账号")}</strong><time>{date(s.published)}</time><p>{s.content || tr("此来源未保存推文文字")}</p><button className="source-link" onClick={() => run(() => api('openSource', { url: s.url }))}>{tr("查看原帖")}<ArrowUpRight size={13}/></button></article>) : <p className="hint">{tr("从本地导入，没有推文来源。")}</p>}</div><button className="export-button" onClick={() => run(() => api('contextMenu', { id, ids: selected.length ? selected : [id] }))}><Copy size={15}/>{tr("复制 / 外部打开")}</button><button className="subtle block" onClick={() => run(async () => { await api('importEditDialog', { parent: id }); refresh(); })}>{tr("导入此图的修改版本")}</button>{detail.parent && <p className="hint">{tr("此项关联一个原始版本。")}</p>}<p className="hint">OCR：{detail.analysis_status === 'done' ? tr("已分析") : detail.analysis_status === 'pending' ? tr("待分析") : tr("此媒体类型暂不适用")}</p></aside>;
}
export function Pagination({ page, pages, change }: {
    page: number;
    pages: number;
    change: (n: number) => void;
}) { return <div className="pagination"><button disabled={page <= 1} onClick={() => change(page - 1)}><ChevronLeft size={16}/>{tr("上一页")}</button><span>{page} / {pages}</span><button disabled={page >= pages} onClick={() => change(page + 1)}>{tr("下一页")}<ChevronRight size={16}/></button></div>; }
export function SettingsView({ stats, run, changed }: {
    stats: Stats;
    run: Run;
    changed: () => void;
}) {
    const [prefs, setPrefs] = useState<any>({}), [settings, setSettings] = useState<any>({}), [result, setResult] = useState('');
    useEffect(() => { api('desktopSettings').then(setPrefs); api('settings').then(setSettings); }, []);
    const save = (values: any) => run(async () => setPrefs(await api('desktopSettings', { save: values })));
    const action = (method: string, args: any = {}) => run(async () => { const r = await api(method, args); if (r && method === 'libraryDialog') {
        api('reloadWindow');
        return;
    } if (r)
        setResult(typeof r === 'object' ? JSON.stringify(r, null, 2) : String(r)); changed(); });
    return <div className="settings-page"><section className="settings-card"><h2>{tr("外观与大屏")}</h2><LanguageSetting run={run}/><div className="setting-row"><label>{tr("界面缩放")}</label><select value={prefs.zoom || 1} onChange={e => save({ zoom: +e.target.value })}>{[.8, 1, 1.1, 1.25, 1.5, 1.75, 2].map(n => <option key={n} value={n}>{Math.round(n * 100)}%</option>)}</select></div><div className="setting-row"><label>{tr("文字大小")}</label><select value={prefs.fontScale || 1} onChange={e => save({ fontScale: +e.target.value })}><option value="1">{tr("标准")}</option><option value="1.15">{tr("较大")}</option><option value="1.3">{tr("大")}</option></select></div><div className="setting-row"><label>{tr("明暗外观")}</label><select value={prefs.theme || 'light'} onChange={e => { save({ theme: e.target.value }); localStorage.setItem('theme', e.target.value); document.documentElement.dataset.theme = e.target.value; }}><option value="light">{tr("浅色")}</option><option value="dark">{tr("深色")}</option></select></div></section><section className="settings-card"><h2>{tr("资料库与存储")}</h2><p className="path">{stats.root}</p><p className="muted">{tr("当前保留 {0} 项 · 原文件约 {1} · 回收站 {2} 项 · 磁盘可用 {3}", [stats.total, bytes(stats.bytes), stats.trash, bytes(stats.freeBytes || 0)])}</p><div className="button-row"><button className="subtle" onClick={() => action('openData')}>{tr("打开位置")}</button><button className="subtle" onClick={() => action('libraryDialog', { mode: 'migrate' })}>{tr("迁移到新位置")}</button><button className="subtle" onClick={() => action('libraryDialog', { mode: 'switch' })}>{tr("选择已有资料库")}</button><button className="subtle" onClick={() => action('libraryDialog', { mode: 'new' })}>{tr("新建资料库")}</button></div><p className="hint">{tr("迁移前暂停采集；完成校验后切换。旧资料库保留，不自动删除。")}</p><div className="button-row"><button className="subtle" onClick={() => action('backupDialog')}>{tr("完整本地备份")}</button><button className="subtle" onClick={() => action('check')}>{tr("检查资料库")}</button><button className="subtle" onClick={() => action('clearCache')}>{tr("清理缩略图缓存")}</button><button className="subtle" onClick={() => action('openMediaRoot')}>{tr("打开媒体树状目录")}</button><button className="subtle" onClick={() => action('organizeStorage')}>{tr("重新整理磁盘目录")}</button></div><p className="hint">{tr("磁盘结构：originals / @账号 / 分类 / 照片·视频·GIF。本地导入和回收站单独存放；多分类、多来源使用硬链接共用文件。待整理 {0} 项。", [stats.storage?.pending || 0])}</p>{stats.storage?.errors?.length > 0 && <p className="error-text">{tr("目录整理存在问题，请点击“重新整理磁盘目录”查看详情。原文件保留。")}</p>}{stats.storage?.aliasWarnings > 0 && <p className="hint">{tr("此磁盘部分目录不能建立硬链接，媒体保留在主位置；其他来源仍可在软件内查找。")}</p>}</section><section className="settings-card"><h2>{tr("本地分析与 AI 找图")}</h2><p>{stats.analysis?.message || tr("模型未安装")} {stats.analysis?.downloading ? `${stats.analysis.downloadProgress}%` : ''}</p><p className="muted">{tr("待识别照片 {0} 张 · 语义索引 {1} 张", [stats.analysis?.pending ?? stats.pending, stats.analysis?.indexed || 0])}</p>{stats.analysis?.error && <p className="error-text">{stats.analysis.error}</p>}<div className="button-row"><button className="subtle" onClick={() => action('analysis', { action: stats.analysis?.paused ? 'resume' : 'pause' })}>{stats.analysis?.paused ? tr("开始 / 继续分析") : tr("暂停分析")}</button><button className="subtle" disabled={stats.analysis?.downloading} onClick={() => action('analysis', { action: 'install' })}>{stats.analysis?.modelReady ? tr("重新下载中文模型") : tr("安装中文搜图模型（约 191 MB）")}</button><button className="subtle" onClick={() => { if (confirm(tr("重新分析照片并重建本地索引？人工标签和备注不会改变。")))
        action('analysis', { action: 'rebuild' }); }}>{tr("重建分析索引")}</button></div><p className="hint">{tr("文字图筛选使用随软件附带的本地 OCR；语义搜索另需中文模型。视频暂不分析整段内容，视频去重仅比较完全相同文件。")}</p></section><section className="settings-card"><h2>{tr("采集与后台运行")}</h2>{[['closeToTray', tr("关闭窗口后缩到托盘继续运行")], ['startAtLogin', tr("随 Windows 启动")], ['notifications', tr("有新增内容或需要处理时通知")]].map(([k, label]) => <label className="checkbox setting-row" key={k}><span>{label}</span><input type="checkbox" checked={!!prefs[k]} onChange={e => save({ [k]: e.target.checked })}/></label>)}<label className="checkbox setting-row"><span>{tr("定时采集总开关")}</span><input type="checkbox" checked={settings.schedulerEnabled !== false} onChange={e => { setSettings({ ...settings, schedulerEnabled: e.target.checked }); action('saveSettings', { schedulerEnabled: e.target.checked }); }}/></label><label>{tr("采集预留磁盘空间（MiB）")}<input aria-label={tr("预留磁盘空间")} type="number" min="16" max="65536" value={settings.minFreeMiB ?? 512} onChange={e => setSettings({ ...settings, minFreeMiB: +e.target.value })}/></label><button className="subtle" onClick={() => action('saveSettings', { minFreeMiB: Math.max(16, Math.min(65536, +settings.minFreeMiB || 512)) })}>{tr("保存空间设置")}</button><label>{tr("采集代理（留空使用系统网络配置）")}<input placeholder="http://127.0.0.1:7897" value={settings.proxy || ''} onChange={e => setSettings({ ...settings, proxy: e.target.value })}/></label><button className="subtle" onClick={() => action('saveSettings', { proxy: settings.proxy || '' })}>{tr("保存网络设置")}</button><p className="hint">{tr("每个账号的定时规则在“采集任务 → 定时计划”中设置。软件完全退出或电脑关机时不执行。")}</p></section><AssistantSettings run={run}/><ProjectFeedback run={run}/><section className="settings-card"><h2>{tr("外部编辑与版本")}</h2><p className="path">{tr("编辑器：")}{prefs.editor || tr("系统默认")}</p><button className="subtle" onClick={() => run(async () => setPrefs({ ...prefs, editor: await api('editorDialog') }))}>{tr("选择编辑器")}</button><p className="hint">{tr("外部编辑会打开副本，使用媒体详情中的“导入修改版本”放回图库。Luma 0.5.1-beta.1 · 本地资料库。")}</p></section>{result && <pre className="operation-result">{result}</pre>}</div>;
}
