import { tr } from './i18n';
import React, { useEffect, useState } from 'react';
import { FolderSync, LoaderCircle } from 'lucide-react';
import { api } from './api';
export function LibrarySwitch() {
    const [state, setState] = useState<any>({ status: 'idle' }), [elapsed, setElapsed] = useState(0), [cancelling, setCancelling] = useState(false), [error, setError] = useState('');
    useEffect(() => { api('librarySwitchStatus').then(setState).catch(() => { }); return (window.luma as any)?.onLibrarySwitch?.((value: any) => { setState(value); if (value.status === 'idle') {
        setCancelling(false);
        setError('');
    } }); }, []);
    useEffect(() => { if (state.status !== 'running')
        return; const tick = () => setElapsed(Math.max(0, Math.floor(Date.now() / 1000 - (state.started || Date.now() / 1000)))); tick(); const timer = setInterval(tick, 1000); return () => clearInterval(timer); }, [state.status, state.started]);
    if (state.status !== 'running')
        return null;
    const phases: Record<string, string> = { recovering:tr('暂停下载文件恢复'),checking: tr("检查目标资料库"), waiting: tr("等待当前读取结束"), pausing: tr("暂停旧库后台分析"), copying: tr("复制并校验资料库文件"), opening: tr("打开目标数据库并检查版本"), saving: tr("保存资料库位置") };
    return <div className="library-switch-backdrop"><section className="library-switch-card" role="dialog" aria-modal="true" aria-labelledby="library-switch-title"><FolderSync size={30}/><h2 id="library-switch-title">{tr("正在切换资料库")}</h2><p role="status"><LoaderCircle className="spin" size={16}/>{phases[state.phase] || tr("正在准备")} · {elapsed}{tr("秒")}</p>{state.path && <p className="path">{state.path}</p>}<p className="hint">{tr("原资料库会保留；目标就绪后才保存新的位置。文件恢复与目录整理会在后台继续。")}</p><button className="subtle" disabled={cancelling} onClick={async () => { setCancelling(true); try {
        await api('cancelLibrarySwitch');
    }
    catch (e) {
        setError((e as Error).message);
        setCancelling(false);
    } }}>{cancelling ? tr("正在安全取消…") : tr("取消切换")}</button>{error && <p className="error-text">{error}</p>}</section></div>;
}
