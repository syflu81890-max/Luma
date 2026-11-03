import { tr } from './i18n';
import React, { useState } from 'react';
import { Images, ChevronsUpDown, FolderOpen } from 'lucide-react';
import { api } from './api';
import { Modal } from './components';
import { Run } from './controls';
export function WorkspaceButton({ initial, run }: {
    initial: any;
    run: Run;
}) {
    const [data, setData] = useState(initial), [open, setOpen] = useState(false), [name, setName] = useState(initial.current.name), [error, setError] = useState(''), [switching, setSwitching] = useState(false);
    const select = (id: string) => { setSwitching(true); setError(''); api('workspaceSelect', { id }).then(() => api('reloadWindow')).catch(e => { setError(e.message); setSwitching(false); }); };
    return <><button className="workspace-brand" aria-label={tr("切换收藏空间")} onClick={() => setOpen(true)}><span className="brand-icon" data-theme-slot="logo">{data.current.logo ? <img src={data.current.logo} alt={tr("空间标识")}/> : <Images size={22}/>}</span><span><strong>Luma</strong><small>{data.current.name}</small></span><ChevronsUpDown size={14}/></button>
 {open && <Modal title={tr("收藏空间")} close={() => !switching && setOpen(false)}><p className="hint">{tr("每个空间使用独立资料库，账号、任务、合集和整理记录分别保存。X 登录暂由当前电脑会话共用，切换不会更换登录账号。")}</p><div className="workspace-list">{data.items.map((w: any) => <button key={w.id} className={w.id === data.current.id ? 'active' : ''} disabled={switching || !w.available && w.id !== data.current.id} onClick={() => w.id !== data.current.id && select(w.id)}><FolderOpen size={18}/><span><strong>{w.name}</strong><small title={w.path}>{w.available ? w.path : tr("资料库离线，请连接存储盘")}</small></span>{w.id === data.current.id && <small>{tr("当前")}</small>}</button>)}</div>
 <label>{tr("当前空间名称")}<input aria-label={tr("收藏空间名称")} value={name} maxLength={40} onChange={e => setName(e.target.value)}/></label><div className="button-row"><button className="subtle" onClick={() => run(async () => setData(await api('workspaceSave', { name })))}>{tr("保存名称")}</button><button className="subtle" onClick={() => run(async () => setData(await api('workspaceLogo')))}>{tr("更换标识")}</button>{data.current.logo && <button className="text-button" onClick={() => run(async () => setData(await api('workspaceLogo', { reset: true })))}>{tr("恢复默认标识")}</button>}</div>
 <p className="hint">{tr("先暂停采集，再切换空间。图片主题接口已预留，本版使用默认界面。")}</p>{error && <div className="error-banner">{error}</div>}<div className="modal-footer"><button className="subtle" disabled={switching} onClick={() => run(async () => { const r = await api('libraryDialog', { mode: 'switch' }); if (r)
            api('reloadWindow'); })}>{tr("连接已有资料库")}</button><button className="primary" disabled={switching} onClick={() => run(async () => { const r = await api('libraryDialog', { mode: 'new' }); if (r)
            api('reloadWindow'); })}>{tr("新建空间")}</button></div></Modal>}</>;
}
