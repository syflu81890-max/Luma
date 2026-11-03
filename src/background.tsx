import { tr } from './i18n';
import React, { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { api, Stats } from './api';
import { Modal } from './components';
import { Run } from './controls';
export function BackgroundWork({ stats, run }: {
    stats: Stats;
    run: Run;
}) {
    const [open, setOpen] = useState(false), [data, setData] = useState<any>(null), [identity, setIdentity] = useState<any>(null);
    useEffect(() => { let live = true; const load = () => api('loginStatus').then(v => live && setIdentity(v)).catch(() => { }); load(); const timer = setInterval(load, 300000); return () => { live = false; clearInterval(timer); }; }, []);
    useEffect(() => { if (!open)
        return; let live = true; const load = () => api('backgroundStatus').then(v => live && setData(v)).catch(() => { }); load(); const timer = setInterval(load, 2000); return () => { live = false; clearInterval(timer); }; }, [open]);
    return <><button className="background-trigger" title={stats.root} onClick={() => setOpen(true)}><Activity size={13}/>{stats.active ? tr("正在采集") : stats.analysis?.busy ? tr("正在分析") : tr("后台状态")}<span>{identity?.handle ? 'X @' + identity.handle : identity?.loggedIn ? tr("X 身份待验证") : tr("X 未登录")}</span></button>{open && <Modal title={tr("后台工作")} close={() => setOpen(false)}><p className="path">{stats.root}</p><div className="background-rows"><div><span>{tr("采集队列")}</span><b>{stats.active ? tr("采集中") : tr("空闲")}{tr("· 排队")}{stats.queued || 0}</b></div><div><span>{tr("本地内容分析")}</span><b>{data?.analysis?.busy ? tr("分析中") : data?.analysis?.paused ? tr("已暂停") : tr("等待新内容")}</b></div><div><span>{tr("语义搜索覆盖")}</span><b>{stats.analysis?.indexed || 0} / {stats.analysis?.total || 0}{tr("张")}</b></div><div><span>{tr("等待语义索引")}</span><b>{stats.analysis?.unindexed || 0}{tr("张")}</b></div><div><span>{tr("相似图检查")}</span><b>{data?.similar?.status === 'running' ? tr("检查中") : tr("空闲")}</b></div><div><span>{tr("账号检测")}</span><b>{data?.health?.status === 'running' ? `${data.health.checked} / ${data.health.total}` : tr("空闲")}</b></div><div><span>{tr("关注读取")}</span><b>{data?.following?.status === 'running' ? tr("读取中") : tr("已停止")} · {data?.following?.total || 0}{tr("个")}</b></div><div><span>{tr("磁盘目录整理")}</span><b>{tr("待处理")}{data?.storage?.pending || 0}</b></div></div><p className="hint">{identity?.message} {identity?.handle ? '@' + identity.handle : ''}</p><div className="button-row"><button className="subtle" onClick={() => run(() => api('login', { home: true }))}>{tr("打开 X 核对身份")}</button><button className="subtle" onClick={() => run(async () => setIdentity(await api('loginStatus', { refresh: true })))}>{tr("刷新登录身份")}</button><button className="subtle" onClick={() => run(async () => { const ids = await api('taskIds', { status: 'active' }); await api('taskBatch', { ids, action: 'pause' }); })}>{tr("暂停全部采集")}</button><button className="subtle" onClick={() => run(() => api('analysis', { action: stats.analysis?.paused ? 'resume' : 'pause' }))}>{stats.analysis?.paused ? tr("继续本地分析") : tr("暂停本地分析")}</button></div></Modal>}</>;
}
