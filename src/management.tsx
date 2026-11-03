import { tr } from './i18n';
import React, { useEffect, useState, useRef } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Clock, Download, Plus, SlidersHorizontal, X } from 'lucide-react';
import { api, Account, Task, Stats, date, bytes, statuses, duration } from './api';
import { Avatar, Empty, Modal, Pagination, RatingFilter } from './components';
import { LimitInput, PageSize, Run, useStored } from './controls';
import './management.css';
import { FollowingDialog } from './following';
type Page<T> = {
    items: T[];
    total: number;
    pages: number;
    page: number;
    counts?: Record<string, number>;
};
type Column = {
    key: string;
    label: string;
    width: number;
    sort?: string;
    optional?: boolean;
};
const accountColumns: Column[] = [{ key: 'identity', label: tr("账号"), width: 240, sort: 'name' }, { key: 'rating', label: tr("评分"), width: 110, sort: 'rating' }, { key: 'categories', label: tr("分类"), width: 175 }, { key: 'media', label: tr("在库照片 / 视频 / GIF"), width: 175, sort: 'count' }, { key: 'checked', label: tr("最近检查 / 本批新增"), width: 185, sort: 'checked' }, { key: 'status', label: tr("更新状态"), width: 130 }, { key: 'schedule', label: tr("定时 / 下次检查"), width: 185, sort: 'next' }, { key: 'added', label: tr("最近有新增"), width: 170, sort: 'added', optional: true }, { key: 'created', label: tr("首次添加"), width: 165, sort: 'new', optional: true }, { key: 'storage', label: tr("在库大小"), width: 125, optional: true }, { key: 'note', label: tr("账号备注"), width: 230, optional: true }, { key: 'actions', label: tr("操作"), width: 260 }];
const taskColumns: Column[] = [{ key: 'identity', label: tr("账号 / 帖子"), width: 245 }, { key: 'mode', label: tr("方式 / 范围"), width: 150 }, { key: 'status', label: tr("状态"), width: 120 }, { key: 'counts', label: tr("新增 / 重复 / 已删跳过"), width: 190 }, { key: 'progress', label: tr("扫描 / 下载量 / 速度"), width: 195 }, { key: 'time', label: tr("时间 / 耗时"), width: 175 }, { key: 'actions', label: tr("操作"), width: 280 }];
const busyStates = ['running', 'queued', 'waiting'];
const shortDate = (s?: string) => s ? new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—';
const modeName: Record<string, string> = { latest: tr("最新更新"), history: tr("扫描历史"), preview: tr("选择性预览"), selected: tr("勾选下载"), import: tr("本地导入"), legacy: tr("旧版记录") };
const defaultRule = () => ({ enabled: true, type: 'interval', hours: 6, time: '09:00', limit: 0, onOpen: true, offset: -new Date().getTimezoneOffset() });
function parseRule(value: string) { try {
    return { ...defaultRule(), enabled: false, ...JSON.parse(value || '{}') };
}
catch {
    return { ...defaultRule(), enabled: false };
} }
function useColumns(key: string, all: Column[]) {
    const [widths, setWidths] = useStored<Record<string, number>>(key + '-widths', {}), [hidden, setHidden] = useStored<string[]>(key + '-hidden', all.filter(c => c.optional).map(c => c.key));
    const columns = all.filter(c => !hidden.includes(c.key)).map(c => ({ ...c, width: widths[c.key] || c.width }));
    const resize = (e: React.PointerEvent, k: string, width: number) => {
        e.preventDefault();
        e.stopPropagation();
        const x = e.clientX;
        const move = (event: PointerEvent) => setWidths({ ...widths, [k]: Math.min(650, Math.max(90, width + event.clientX - x)) });
        const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', end);
        window.addEventListener('pointercancel', end);
    };
    const settings = <details className="column-menu"><summary><SlidersHorizontal size={14}/>{tr("显示列")}</summary><div>{all.filter(c => !['identity', 'actions'].includes(c.key)).map(c => <label key={c.key}><input type="checkbox" checked={!hidden.includes(c.key)} onChange={e => setHidden(e.target.checked ? hidden.filter(k => k !== c.key) : [...hidden, c.key])}/>{c.label}</label>)}<button onClick={() => { setWidths({}); setHidden(all.filter(c => c.optional).map(c => c.key)); }}>{tr("恢复默认列宽与列")}</button></div></details>;
    return { columns, resize, settings };
}
export function TasksQueue({ refresh, run, changed, initialAccount = '', openAccount, openBatch }: {
    refresh: number;
    run: Run;
    changed: () => void;
    initialAccount?: string;
    openAccount: (id: string) => void;
    openBatch: (t: Task) => void;
}) {
    const [page, setPage] = useState(1), [size, setSize] = useStored('tasks-page-size', 100), [density, setDensity] = useStored('table-density', 'compact'), [status, setStatus] = useState('active'), [query, setQuery] = useState(''), [account, setAccount] = useState(initialAccount), [data, setData] = useState<Page<Task>>({ items: [], total: 0, pages: 1, page: 1, counts: {} }), [selected, setSelected] = useState<string[]>([]), [expanded, setExpanded] = useState<string[]>([]), [error, setError] = useState(''), [reload, setReload] = useState(0), [result, setResult] = useState<any>(null), [preview, setPreview] = useState<Task | null>(null);
    const [showFollowing, setShowFollowing] = useState(false), [showSchedules, setShowSchedules] = useState(false), [scheduleIds, setScheduleIds] = useState<string[]>([]), [scheduleAccount, setScheduleAccount] = useState<Account>();
    const table = useColumns('tasks', taskColumns), filters = { status, q: query, account }, key = JSON.stringify(filters), counts = data.counts || {};
    const load = () => { setReload(n => n + 1); changed(); };
    useEffect(() => { let alive = true; api('taskPage', { ...filters, page, limit: size }).then(d => { if (alive) {
        setData(d);
        setError('');
    } }).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [key, page, size, refresh, reload]);
    useEffect(() => { setSelected([]); setPage(1); }, [key]);
    const batch = (action: string, ids = selected) => run(async () => { if (action === 'cancel' && !confirm(tr("取消 {0} 个任务？已下载的媒体会保留。", [ids.length])))
        return; const r = await api('taskBatch', { ids, action }); setResult(r); load(); return r; });
    const cell = (t: Task, k: string) => {
        if (k === 'identity')
            return <div className="task-identity"><button className="expand-row" aria-label={tr("任务详情 ") + t.id} onClick={() => setExpanded(expanded.includes(t.id) ? expanded.filter(id => id !== t.id) : [...expanded, t.id])}>{expanded.includes(t.id) ? <ChevronDown size={15}/> : <ChevronRight size={15}/>}</button><span><button title={t.url} onClick={() => t.account ? openAccount(t.account) : setExpanded([...expanded, t.id])}>{t.alias || t.name || t.handle || t.url}</button><small title={t.url}>{t.handle ? '@' + t.handle : t.url}</small></span></div>;
        if (k === 'mode')
            return <div className="two-line"><span>{modeName[t.mode] || t.mode}</span><small>{t.mode === 'import' ? tr("{0} 个文件", [t.limit_count]) : t.limit_count ? tr("最多 {0} 项", [t.limit_count]) : tr("不限数量")} · {t.origin === 'schedule' ? tr("定时") : tr("手动")}</small></div>;
        if (k === 'status')
            return <div className="two-line"><span className={'status-tag ' + t.status}>{statuses[t.status] || t.status}</span>{t.status === 'waiting' && <small title={t.retry_at}>{shortDate(t.retry_at)}{tr("重试")}</small>}</div>;
        if (k === 'counts')
            return <div className="task-counts"><b title={tr("新增入库")}>{t.imported}</b><span>/ {t.duplicates} / {t.excluded}</span></div>;
        if (k === 'progress')
            return <div className="two-line"><span>{tr("扫描")}{t.scanned} · {bytes(t.downloaded_bytes || 0)}</span><small>{t.status === 'running' ? (t.speed > 0 ? bytes(t.speed) + '/s' : tr("正在检查 / 下载…")) : '—'}</small></div>;
        if (k === 'time')
            return <div className="two-line"><span title={date(t.created)}>{shortDate(t.created)}</span><small>{duration(t.elapsed || 0)} · {t.status === 'running' ? tr("本轮运行中") : tr("累计运行")}</small></div>;
        return <div className="row-actions">{['needs_login', 'needs_access'].includes(t.status) && <button onClick={() => run(() => api('login', { home: t.status === 'needs_access' }))}>{t.status === 'needs_access' ? tr("核对身份") : tr("登录 X")}</button>}{t.mode === 'preview' && <button className="text-action" onClick={() => setPreview(t)}>{tr("选择媒体")}</button>}{t.mode !== 'import' && <>{busyStates.includes(t.status) ? <button onClick={() => batch('pause', [t.id])}>{tr("暂停")}</button> : ['paused', 'failed', 'needs_login', 'needs_access', 'partial', 'cancelled'].includes(t.status) && <button className="text-action" onClick={() => run(async () => { await api('taskBatch', { ids: [t.id], action: 'resume' }); load(); })}>{t.status === 'needs_login' ? tr("重试") : t.status === 'paused' ? tr("恢复") : t.status === 'partial' ? tr("继续补齐") : tr("重试")}</button>}{!['completed', 'cancelled'].includes(t.status) && <button onClick={() => batch('cancel', [t.id])}>{tr("取消")}</button>}</>}{t.account && <button onClick={() => run(async () => { setScheduleAccount(await api<Account>('account', { id: t.account })); setScheduleIds([t.account]); })}>{tr("定时")}</button>}{t.status === 'completed' && <button onClick={() => openBatch(t)}>{tr("查看结果")}</button>}{t.mode !== 'import' && !busyStates.includes(t.status) && <button title={tr("读取软件内已登录 X 页面中可见的媒体")} onClick={() => run(async () => { const r = await api('browserCollect', { id: t.id }); setResult({ succeeded: 0, skipped: 0, errors: [], message: r.message }); load(); })}>{tr("浏览器补采")}</button>}<button onClick={() => setExpanded(expanded.includes(t.id) ? expanded.filter(id => id !== t.id) : [...expanded, t.id])}>{tr("详情")}</button></div>;
    };
    return <div className={'management ' + density}>
  <div className="queue-tabs">{[['active', tr("进行中"), ['running', 'queued', 'waiting'].reduce((n, s) => n + (counts[s] || 0), 0)], ['attention', tr("需处理"), ['paused', 'partial', 'failed', 'needs_login', 'needs_access', 'blocked_account'].reduce((n, s) => n + (counts[s] || 0), 0)], ['completed', tr("已完成"), counts.completed || 0], ['all', tr("全部"), Object.values(counts).reduce((a, b) => a + b, 0)]].map(([s, label, n]) => <button key={s} className={status === s ? 'active' : ''} onClick={() => setStatus(String(s))}>{label}<b>{n}</b></button>)}</div>
  <div className="management-toolbar"><div className="filter-inline"><input aria-label={tr("搜索采集任务")} placeholder={tr("搜索账号或帖子…")} value={query} onChange={e => setQuery(e.target.value)}/><select aria-label={tr("任务状态")} value={status} onChange={e => setStatus(e.target.value)}><option value="active">{tr("进行中")}</option><option value="attention">{tr("需处理")}</option><option value="all">{tr("全部状态")}</option>{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>{account && <button className="subtle" onClick={() => setAccount('')}>{tr("仅此账号 ×")}</button>}<button className="text-button" onClick={() => run(async () => { const ids = await api<string[]>('taskIds', filters); if (confirm(tr("选择全部筛选结果，共 {0} 个任务？", [ids.length])))
        setSelected(ids); })}>{tr("选择全部筛选结果")}</button></div><div className="table-options-end">{table.settings}<select aria-label={tr("任务行高")} value={density} onChange={e => setDensity(e.target.value)}><option value="compact">{tr("紧凑")}</option><option value="comfortable">{tr("舒适")}</option></select><PageSize value={size} onChange={n => { setSize(n); setPage(1); }}/></div></div>
  <div className="task-primary-actions"><button className="primary" onClick={() => run(async () => { const r = await api('collectAll'); setResult(r); load(); })}><Download size={15}/>{tr("一键提取最新")}</button><button className="subtle" onClick={() => setShowFollowing(true)}>{tr("导入我的关注")}</button><button className="subtle" onClick={() => setShowSchedules(true)}><Clock size={15}/>{tr("定时计划")}</button><span className="hint">{tr("仅更新普通账号；已在队列中的任务自动跳过。")}</span></div><CompletionControls run={run}/>
  {selected.length > 0 && <div className="management-selection"><strong>{tr("已选")}{selected.length}{tr("个任务")}</strong><button onClick={() => { setScheduleAccount(undefined); setScheduleIds([...new Set(data.items.filter(t => selected.includes(t.id) && t.account).map(t => t.account))]); }}>{tr("所选账号定时")}</button><button onClick={() => batch('pause')}>{tr("暂停")}</button><button onClick={() => batch('resume')}>{tr("恢复 / 继续")}</button><button onClick={() => batch('retryFailed')}>{tr("仅重试失败")}</button><button onClick={() => batch('cancel')}>{tr("取消任务")}</button><button onClick={() => { if (confirm(tr("隐藏所选的完成/取消记录？采集批次关系和媒体仍会保留。")))
        batch('hide'); }}>{tr("隐藏完成记录")}</button><button onClick={() => setSelected([])}>{tr("取消选择")}</button></div>}
  {error && <div className="error-banner">{error}<button onClick={load}>{tr("重试")}</button></div>}<BatchResult value={result} close={() => setResult(null)}/>
  {data.items.length ? <div className="table-scroll"><table className="data-table task-table" style={{ width: 42 + table.columns.reduce((n, c) => n + c.width, 0) }}><colgroup><col style={{ width: 42 }}/>{table.columns.map(c => <col key={c.key} style={{ width: c.width }}/>)}</colgroup><thead><tr><th className="select-cell"><CheckAll ids={data.items.map(t => t.id)} selected={selected} onChange={setSelected}/></th>{table.columns.map(c => <th key={c.key} className={c.key === 'identity' ? 'identity-cell' : c.key === 'actions' ? 'actions-cell' : ''}>{c.label}<span className="column-resize" onPointerDown={e => table.resize(e, c.key, c.width)}/></th>)}</tr></thead><tbody>{data.items.map(t => <React.Fragment key={t.id}><tr className={selected.includes(t.id) ? 'selected-row' : ''}><td className="select-cell"><input type="checkbox" aria-label={tr("选择任务 ") + t.id} checked={selected.includes(t.id)} onChange={e => setSelected(e.target.checked ? [...selected, t.id] : selected.filter(id => id !== t.id))}/></td>{table.columns.map(c => <td key={c.key} className={c.key === 'identity' ? 'identity-cell' : c.key === 'actions' ? 'actions-cell' : ''}>{cell(t, c.key)}</td>)}</tr>{expanded.includes(t.id) && <tr className="task-expanded"><td colSpan={table.columns.length + 1}><strong>{t.url}</strong><p>{t.message || tr("等待采集")}</p><TaskExplanation task={t}/><p>{tr("范围：")}{taskRange(t)}{tr("· 已扫描")}{t.scanned}{tr("· 新增")}{t.imported}{tr("· 重复")}{t.duplicates}{tr("· 已删跳过")}{t.excluded}{tr("· 导入失败")}{t.failed || 0}</p>{t.retry_at && <p>{tr("下次重试：")}{date(t.retry_at)}</p>}<small>{tr("创建")}{date(t.created)}{tr("· 最近活动")}{date(t.updated)}</small></td></tr>}</React.Fragment>)}</tbody></table></div> : <Empty title={status === 'active' ? tr("当前没有进行中的任务") : tr("没有匹配的任务")} text={status === 'active' ? tr("已完成记录已收起，可点击上方“已完成”查看。") : tr("调整状态或账号筛选后再试。")}/>}
  <div className="table-footer"><span>{data.total}{tr("条 · 已选")}{selected.length}</span><Pagination page={data.page} pages={data.pages} change={setPage}/></div>
  {showFollowing && <FollowingDialog run={run} close={() => setShowFollowing(false)} changed={load}/>}
  {showSchedules && <ScheduleManager close={() => setShowSchedules(false)} run={run} changed={load}/>}
 {scheduleIds.length > 0 && <ScheduleDialog ids={scheduleIds} account={scheduleAccount} close={() => setScheduleIds([])} run={run} done={load}/>}
 {preview && <CandidateDialog task={preview} run={run} close={() => setPreview(null)} changed={load}/>}
 </div>;
}
function TaskExplanation({ task }: {
    task: Task;
}) { let r: any = {}; try {
    r = JSON.parse(task.result_json || '{}');
}
catch { } const c = r.counts || {}, reason: Record<string, string> = { access_denied: tr("访问权限不足"), login_expired: tr("登录待验证"), rate_limited: tr("平台请求受限"), engine_error: tr("采集接口异常"), disk_full: tr("磁盘空间不足"), empty_unverified: tr("空响应尚未验证"), empty_pending: tr("上轮范围未补齐"), browser_empty: tr("页面未发现可采集媒体") }; return <div className="task-explanation"><span>{tr("本轮扫描：已存在")}{c.known || 0}{tr("· 已删排除")}{c.excluded || 0}{tr("· 日期/类型过滤")}{c.filter || 0}{tr("· 旧采集范围")}{c.old || 0}{tr("· 页面重复")}{c.duplicate || 0}</span><small>{r.complete ? tr("本轮检查已完成") : task.status === 'running' ? tr("正在检查，尚未确认完整范围") : tr("本轮尚未确认完整范围；继续时保留已入库内容")}{task.reason_code ? ' · ' + (reason[task.reason_code] || tr("需要检查采集结果")) : ''}</small></div>; }
function taskRange(t: Task) { try {
    const o = JSON.parse(t.options || '{}');
    return tr("{0}，{1}，{2} 至 {3}，{4}", [modeName[t.mode] || t.mode, t.limit_count ? tr("上限 ") + t.limit_count : tr("不限数量"), o.from || tr("最早"), o.to || tr("最新"), (o.kinds || ['image', 'video', 'gif']).map((s: string) => ({ image: tr("照片"), video: tr("视频"), gif: 'GIF' }[s] || s)).join('/')]);
}
catch {
    return modeName[t.mode] || t.mode;
} }
function CandidateThumb({ item }: {
    item: any;
}) {
    const [src, setSrc] = useState(''), ref = useRef<HTMLDivElement>(null);
    useEffect(() => { let alive = true; const observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) {
        observer.disconnect();
        api<string>('candidateImage', { task: item.task, key: item.media_key }).then(s => alive && setSrc(s)).catch(() => { });
    } }, { rootMargin: '80px' }); if (ref.current)
        observer.observe(ref.current); return () => { alive = false; observer.disconnect(); }; }, [item.task, item.media_key]);
    return <div className="candidate-thumb" ref={ref}>{src ? <img src={src} alt={tr("候选媒体")}/> : <span>{tr("视频 / 待预览")}</span>}</div>;
}
function CandidateDialog({ task, run, close, changed }: {
    task: Task;
    run: Run;
    close: () => void;
    changed: () => void;
}) {
    const [page, setPage] = useState(1), [data, setData] = useState<Page<any>>({ items: [], total: 0, pages: 1, page: 1 }), [selected, setSelected] = useState<string[]>([]), [paused, setPaused] = useState(!busyStates.includes(task.status)), [error, setError] = useState('');
    useEffect(() => { let live = true; api('candidatePage', { id: task.id, page }).then(d => live && setData(d)).catch(e => live && setError(e.message)); return () => { live = false; }; }, [task.id, page, paused]);
    return <Modal title={tr("选择要下载的媒体")} wide close={close}><p className="hint">{tr("共")}{data.total}{tr("个候选 · 已选")}{selected.length}{tr("项，每页 100 项。选择会跨页保留。")}</p>{error && <p className="error-text">{error}</p>}{!paused && <div className="notice">{tr("预览任务仍可能在采集，请暂停或等待完成后下载所选。")}<button onClick={() => run(async () => { await api('taskBatch', { ids: [task.id], action: 'pause' }); setPaused(true); changed(); })}>{tr("暂停预览并选择")}</button></div>}<div className="candidate-grid">{data.items.map(c => <button key={c.media_key} className={selected.includes(c.media_key) ? 'picked' : ''} onClick={() => setSelected(selected.includes(c.media_key) ? selected.filter(k => k !== c.media_key) : [...selected, c.media_key])}><CandidateThumb item={c}/><span>{selected.includes(c.media_key) ? tr("✓ 已选") : tr("选择")} · {c.media_key}</span></button>)}</div><Pagination page={page} pages={data.pages} change={setPage}/><div className="modal-footer"><button className="subtle" onClick={() => setSelected([...new Set([...selected, ...data.items.map(i => i.media_key)])])}>{tr("选择当前页")}</button><button className="subtle" onClick={() => run(async () => { const ids = await api<string[]>('candidateIds', { id: task.id }); setSelected(ids); })}>{tr("选择全部候选")}</button><button className="primary" disabled={!selected.length || !paused} onClick={() => run(async () => { await api('addTask', { url: task.url, mode: 'selected', limit: 0, selected: selected.map(key => ({ task: task.id, key })) }); changed(); close(); })}>{tr("下载所选")}{selected.length}{tr("项")}</button></div></Modal>;
}
export function useCompletion() {
    const [state, setState] = useState<any>({ phase: 'off', action: 'none' });
    useEffect(() => { let live = true; api('completionState').then(s => live && setState(s)).catch(() => { }); const stop = (window.luma as any)?.onCompletion?.(setState); return () => { live = false; stop?.(); }; }, []);
    return state;
}
function CompletionControls({ run }: {
    run: Run;
}) {
    const state = useCompletion(), [action, setAction] = useState('shutdown'), [waitAnalysis, setWaitAnalysis] = useState(false), armed = ['waiting', 'countdown', 'preparing'].includes(state.phase);
    return <div className={'completion-controls ' + (armed ? 'armed' : '')}><Clock size={16}/><span>{tr("本轮完成后")}</span><select aria-label={tr("完成后动作")} disabled={armed} value={action} onChange={e => setAction(e.target.value)}><option value="shutdown">{tr("关机")}</option><option value="sleep">{tr("睡眠")}</option></select><label><input type="checkbox" disabled={armed} checked={waitAnalysis} onChange={e => setWaitAnalysis(e.target.checked)}/>{tr("等待本地分析完成")}</label><button className={armed ? 'subtle' : 'text-action'} onClick={() => run(() => api('completionPlan', { action: armed ? 'none' : action, waitAnalysis }))}>{armed ? tr("取消本轮动作") : tr("启用本轮")}</button><small>{armed ? `${state.complete || 0} / ${state.total || 0} · ${state.message}` : state.message || tr("默认不执行；只对本轮启用，退出后失效")}</small></div>;
}
export function CompletionBanner() {
    const state = useCompletion();
    if (!['countdown', 'preparing', 'blocked', 'error'].includes(state.phase))
        return null;
    return <div className={'completion-banner ' + state.phase} role="alert"><Clock size={21}/><div><strong>{state.phase === 'countdown' ? tr("{0} 秒后{1}", [state.remaining, state.action === 'shutdown' ? tr("关机") : tr("睡眠")]) : state.phase === 'preparing' ? tr("正在安全保存") : tr("完成后动作已停止")}</strong><p>{state.message}</p></div>{['countdown', 'preparing'].includes(state.phase) ? <button onClick={() => api('completionPlan', { action: 'none' }).catch(() => { })}>{tr("取消本次动作")}</button> : <button aria-label={tr("关闭完成后动作提示")} onClick={() => api('completionPlan', { action: 'none' }).catch(() => { })}><X size={16}/></button>}</div>;
}
function CheckAll({ ids, selected, onChange }: {
    ids: string[];
    selected: string[];
    onChange: (s: string[]) => void;
}) {
    const ref = useRef<HTMLInputElement>(null), count = ids.filter(id => selected.includes(id)).length;
    useEffect(() => { if (ref.current)
        ref.current.indeterminate = count > 0 && count < ids.length; }, [count, ids.length]);
    return <input ref={ref} type="checkbox" aria-label={tr("全选本页")} checked={!!ids.length && count === ids.length} onChange={e => onChange(e.target.checked ? [...new Set([...selected, ...ids])] : selected.filter(id => !ids.includes(id)))}/>;
}
function BatchResult({ value, close }: {
    value: any;
    close: () => void;
}) { if (!value)
    return null; return <div className={'batch-result ' + (value.errors?.length ? 'has-errors' : '')} role="status"><span>{value.message && <>{value.message}<br /></>}{tr("完成")}{value.succeeded}{tr("· 跳过")}{value.skipped}{tr("· 失败")}{value.errors?.length || 0}</span>{value.errors?.length > 0 && <details><summary>{tr("查看失败项")}</summary>{value.errors.map((e: any) => <p key={e.id}>{e.id}：{e.message}</p>)}</details>}<button aria-label={tr("关闭操作结果")} onClick={close}><X size={14}/></button></div>; }
function InlineCategories({ account, save }: {
    account: Account;
    save: (value: string) => void;
}) {
    const [value, setValue] = useState(account.categories);
    const editing = useRef(false), cancelled = useRef(false);
    useEffect(() => { if (!editing.current)
        setValue(account.categories); }, [account.categories]);
    return <input className="inline-categories" aria-label={tr("分类 @") + account.handle} title={tr("逗号分隔，回车或离开输入框保存")} value={value} placeholder={tr("添加分类…")} onFocus={() => { editing.current = true; cancelled.current = false; }} onChange={e => setValue(e.target.value)} onBlur={() => { editing.current = false; if (cancelled.current)
        return; if (value !== account.categories)
        save(value); }} onKeyDown={e => { if (e.key === 'Enter')
        e.currentTarget.blur(); if (e.key === 'Escape') {
        cancelled.current = true;
        setValue(account.categories);
        e.currentTarget.blur();
    } }}/>;
}
export function ScheduleDialog({ ids, account, close, run, done }: {
    ids: string[];
    account?: Account;
    close: () => void;
    run: Run;
    done: () => void;
}) {
    const [rule, setRule] = useState<any>(() => account ? parseRule(account.schedule) : defaultRule());
    return <Modal title={ids.length > 1 ? tr("批量定时 · {0} 个账号", [ids.length]) : tr("账号定时采集")} close={close}><label className="checkbox"><input type="checkbox" checked={rule.enabled} onChange={e => setRule({ ...rule, enabled: e.target.checked })}/>{tr("启用自动更新")}</label><div className="form-row"><label>{tr("更新方式")}<select value={rule.type} onChange={e => setRule({ ...rule, type: e.target.value })}><option value="interval">{tr("间隔更新")}</option><option value="daily">{tr("每天固定时间")}</option></select></label>{rule.type === 'daily' ? <label>{tr("本地时间")}<input type="time" value={rule.time} onChange={e => setRule({ ...rule, time: e.target.value })}/></label> : <label>{tr("间隔小时")}<input type="number" min=".5" step=".5" value={rule.hours} onChange={e => setRule({ ...rule, hours: +e.target.value })}/></label>}</div><label>{tr("每次数量上限")}<LimitInput value={rule.limit} onChange={limit => setRule({ ...rule, limit })}/></label><label className="checkbox"><input type="checkbox" checked={rule.onOpen} onChange={e => setRule({ ...rule, onOpen: e.target.checked })}/>{tr("保存后立即检查一次")}</label><p className="hint">{tr("在软件或托盘运行期间执行。启用本轮完成后关机时，未来定时暂缓。")}</p><div className="modal-footer"><button className="primary" onClick={() => run(async () => { const result = await api('accountBatch', { ids, action: 'schedule', rule }); done(); if (result.errors.length)
        throw Error(result.errors.map((e: any) => e.message).join('；')); close(); })}>{tr("保存规则")}</button></div></Modal>;
}
function ScheduleManager({ close, run, changed }: {
    close: () => void;
    run: Run;
    changed: () => void;
}) {
    const [data, setData] = useState<Page<Account>>({ items: [], total: 0, pages: 1, page: 1 }), [page, setPage] = useState(1), [query, setQuery] = useState(''), [scheduled, setScheduled] = useState(''), [selected, setSelected] = useState<string[]>([]), [reload, setReload] = useState(0), [editor, setEditor] = useState<Account>(), [editingIds, setEditingIds] = useState<string[]>([]), [error, setError] = useState('');
    useEffect(() => { let live = true; api('accounts', { q: query, scheduled, page, limit: 100, pool: 'normal', sort: 'name', direction: 'asc' }).then(r => live && setData(r)).catch(e => live && setError(e.message)); return () => { live = false; }; }, [query, scheduled, page, reload]);
    const load = () => { setReload(n => n + 1); changed(); };
    return <><Modal title={tr("定时采集计划")} wide close={close}><p className="hint">{tr("定时规则统一在采集任务里管理。封禁账号自动停用采集，原规则保留；软件或托盘运行期间执行。")}</p><div className="filter-inline"><input aria-label={tr("搜索定时账号")} placeholder={tr("搜索账号…")} value={query} onChange={e => { setQuery(e.target.value); setPage(1); }}/><select value={scheduled} onChange={e => { setScheduled(e.target.value); setPage(1); }}><option value="">{tr("全部账号")}</option><option value="on">{tr("已开启定时")}</option><option value="off">{tr("未开启定时")}</option></select><button className="subtle" onClick={() => { setEditor(undefined); setEditingIds(selected.length ? selected : data.items.map(a => a.id)); }}>{tr("批量设置")}{selected.length ? tr(" · {0} 个", [selected.length]) : tr("本页")}</button></div>{error && <p className="error-text">{error}</p>}<div className="schedule-list">{data.items.map(a => { const rule = parseRule(a.schedule); return <div key={a.id}><input type="checkbox" aria-label={tr("选择定时 @") + a.handle} checked={selected.includes(a.id)} onChange={e => setSelected(e.target.checked ? [...selected, a.id] : selected.filter(id => id !== a.id))}/><span><strong>{a.alias || a.name || a.handle}</strong><small>@{a.handle} · {rule.enabled ? (rule.type === 'daily' ? tr("每天 {0}", [rule.time]) : tr("每 {0} 小时", [rule.hours])) : tr("未开启")} · {a.auto_paused ? tr("手动暂停") : rule.enabled ? tr("下次 {0}", [shortDate(a.next_run)]) : tr("等待设置")}</small></span><button onClick={() => { setEditor(a); setEditingIds([a.id]); }}>{tr("编辑")}</button><button onClick={() => run(async () => { await api('accountBatch', { ids: [a.id], action: 'scheduleToggle', enabled: !rule.enabled }); load(); })}>{rule.enabled ? tr("关闭") : tr("开启")}</button></div>; })}</div><Pagination page={data.page} pages={data.pages} change={setPage}/></Modal>{editingIds.length > 0 && <ScheduleDialog ids={editingIds} account={editor} close={() => setEditingIds([])} run={run} done={load}/>}</>;
}
