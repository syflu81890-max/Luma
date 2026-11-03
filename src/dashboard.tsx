import { tr } from './i18n';
import React, { useEffect, useState } from 'react';
import { ArrowUpRight, Download, FolderOpen, Images, Users, ShieldAlert, Clock, Minus, Sparkles } from 'lucide-react';
import { api, Stats, date, statuses } from './api';
import { Run } from './controls';
export function Dashboard({ stats, run, navigate, collect, accounts, changed }: {
    stats: Stats;
    run: Run;
    navigate: (view: string) => void;
    collect: () => void;
    accounts: (pool: string, stale?: boolean) => void;
    changed: () => void;
}) {
    const [data, setData] = useState<any>(null), [result, setResult] = useState('');
    useEffect(() => { let live = true; const load = () => api('dashboard').then(r => live && setData(r)).catch(() => { }); load(); const timer = setInterval(load, 15000); return () => { live = false; clearInterval(timer); }; }, []);
    const trend = Array.from({ length: 7 }, (_, n) => { const d = new Date(); d.setDate(d.getDate() - 6 + n); const key = [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-'); return { day: key, label: `${d.getMonth() + 1}/${d.getDate()}`, count: data?.trend.find((v: any) => v.day === key)?.count || 0 }; }), max = Math.max(1, ...trend.map(v => v.count));
    const update = () => run(async () => { const r = await api('collectAll'); setResult(tr("已加入 {0} 个更新任务，跳过 {1} 个已有任务{2}", [r.succeeded, r.skipped, r.errors.length ? '，' + r.errors.length + tr(" 项需检查") : ''])); changed(); });
    return <div className="dashboard"><div className="dashboard-numbers"><button onClick={() => navigate('all')}><Images /><small>{tr("在库媒体")}</small><strong>{stats.offline ? tr("离线") : stats.root ? stats.total.toLocaleString() : '…'}</strong><span>{tr("今日新增 +")}{data?.todayAdded ?? '…'}</span></button><button onClick={() => accounts('normal')}><Users /><small>{tr("收集的账号")}</small><strong>{data ? Math.max(0, (data.accounts?.total || 0) - (data.accounts?.suspended || 0)) : '…'}</strong><span>{tr("按头像和合集查看")}<ArrowUpRight size={13}/></span></button><button onClick={() => navigate('tasks')}><Download /><small>{tr("等待 / 正在采集")}</small><strong>{data ? ['queued', 'running', 'waiting'].reduce((n, k) => n + (data.tasks[k] || 0), 0) : '…'}</strong><span>{tr("进入采集任务")}<ArrowUpRight size={13}/></span></button><button className="attention-metric" onClick={() => accounts('suspended')}><ShieldAlert /><small>{tr("封禁池")}</small><strong>{data?.accounts?.suspended || 0}</strong><span>{tr("单独检测，避免误选")}</span></button></div>
 <div className="dashboard-actions"><button className="primary" onClick={update}><Download size={17}/>{tr("一键提取最新")}</button><button className="subtle" onClick={collect}><PlusIcon />{tr("添加采集")}</button><button className="subtle" onClick={() => accounts('normal', true)}><Clock size={16}/>{tr("七天未检查 ·")}{data?.accounts?.stale || 0}</button><button className="subtle" onClick={() => navigate('similar')}><Sparkles size={16}/>{tr("整理相似图片")}</button></div>{result && <p className="notice" role="status">{result}</p>}
 <div className="dashboard-lower"><section className="dashboard-panel"><div className="dashboard-panel-title"><h3>{tr("最近七天入库")}</h3><small>{trend.reduce((n, v) => n + v.count, 0).toLocaleString()}{tr("项")}</small></div><div className="intake-chart" role="img" aria-label={trend.map(v => v.label + ' ' + v.count + tr("项")).join('，')}>{trend.map(v => <div key={v.day}><span>{v.count || ''}</span><i style={{ height: Math.max(3, v.count / max * 120) }}/><small>{v.label}</small></div>)}</div></section><section className="dashboard-panel"><div className="dashboard-panel-title"><h3>{tr("最近更新")}</h3><button onClick={() => navigate('tasks')}>{tr("查看全部")}<ArrowUpRight size={13}/></button></div>{data?.recent?.length ? data.recent.map((t: any) => <button className="recent-update" key={t.id} onClick={() => navigate('tasks')}><div><strong>{t.alias || t.name || t.handle || tr("本地任务")}</strong><small>{date(t.updated)}</small></div><span>+{t.imported || 0}<small>{statuses[t.status] || t.status}</small></span></button>) : <p className="muted">{tr("开始采集后，更新记录会显示在这里。")}</p>}</section></div></div>;
}
function PlusIcon() { return <span style={{ fontSize: 18, lineHeight: 1 }}>+</span>; }
