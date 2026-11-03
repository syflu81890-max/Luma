import { tr } from './i18n';
import React, { useEffect, useState } from 'react';
import { api } from './api';
export function AssistantSettings({ run }: {
    run: (f: () => Promise<any>) => Promise<any>;
}) {
    const [state, setState] = useState<any>(null), [port, setPort] = useState(48120);
    const load = async () => { const r = await api('assistantStatus'); setState(r); setPort(r.port); };
    useEffect(() => { load().catch(() => { }); }, []);
    const configure = (values: any) => run(async () => { const r = await api('assistantConfigure', values); setState(r); setPort(r.port); });
    return <section className="settings-card assistant-settings"><h2>{tr("本机助手连接")}</h2><p className="muted">{tr("允许这台电脑上的助手读取图库、生成整理计划、移入回收站，以及交接 AI 改图任务。")}</p><label className="checkbox setting-row"><span>{tr("启用本地管理端口")}</span><input aria-label={tr("启用本地管理端口")} type="checkbox" checked={!!state?.enabled} onChange={e => configure({ enabled: e.target.checked })}/></label><div className="form-row"><label>{tr("端口（0 为自动分配）")}<input aria-label={tr("本地管理端口")} type="number" min="0" max="65535" value={port} onChange={e => setPort(+e.target.value)}/></label><button className="subtle" onClick={() => configure({ port })}>{tr("保存端口")}</button></div><p className="path">{state?.running ? state.url : state?.enabled ? tr("尚未连接") : tr("已关闭")}</p>{state?.error && <p className="error-text">{state.error}</p>}<p className="path">{tr("连接文件：")}{state?.connectionFile || tr("读取中…")}</p><div className="button-row"><button className="subtle" onClick={() => run(() => api('assistantCopyConnection'))}>{tr("复制连接文件路径")}</button><button className="subtle" onClick={() => configure({ rotate: true })}>{tr("更换连接密钥")}</button><button className="subtle" onClick={() => run(load)}>{tr("刷新状态")}</button></div><p className="hint">{tr("只监听 127.0.0.1；连接文件中的随机密钥用于本机授权。关闭或更换密钥会使旧连接失效。AI 改图由当前对话里的图片工具执行，Luma 保留原件并导入新版本。")}</p></section>;
}
