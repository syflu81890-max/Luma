import { tr } from './i18n';
import React from 'react';
import { api } from './api';
import { Language, language, storeLanguage } from './i18n';
import { Run } from './controls';
export function LanguageSetting({ run }: {
    run: Run;
}) {
    return <><div className="setting-row"><label htmlFor="interface-language">{tr("界面语言 / Language")}</label><select id="interface-language" value={language()} onChange={e => { const value = e.target.value as Language; run(async () => { await api('desktopSettings', { save: { language: value } }); storeLanguage(value); api('reloadWindow'); }); }}><option value="system">{tr("跟随系统")}</option><option value="zh-CN">{tr("简体中文")}</option><option value="en">English</option></select></div><p className="hint">{tr("语言切换会重新加载界面，保留当前资料库、任务与私人备注。")}</p></>;
}
export function ProjectFeedback({ run }: {
    run: Run;
}) {
    return <section className="settings-card"><h2>{tr("帮助与反馈")}</h2><p className="hint">{tr("欢迎用中文或英文反馈问题和建议。请不要上传私人照片、资料库、登录凭据或连接密钥。")}</p><div className="button-row"><button className="subtle" onClick={() => run(() => api('projectLink', { page: 'bug' }))}>{tr("报告问题")}</button><button className="subtle" onClick={() => run(() => api('projectLink', { page: 'feature' }))}>{tr("提出建议")}</button><button className="subtle" onClick={() => run(() => api('projectLink', { page: 'source' }))}>{tr("查看源码")}</button><button className="subtle" onClick={() => run(() => api('projectLink', { page: 'license' }))}>{tr("开源许可证")}</button></div></section>;
}
