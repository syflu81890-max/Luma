import { tr } from './i18n';
import React from 'react';
import { readStored, writeStored } from './persistence';
export type Run = (f: () => Promise<any>) => Promise<any>;
export function LimitInput({ value, onChange }: {
    value: number;
    onChange: (n: number) => void;
}) {
    const custom = ![0, 100, 500, 1000].includes(value);
    return <div className="limit-input"><select aria-label={tr("采集数量上限")} value={custom ? 'custom' : value} onChange={e => onChange(e.target.value === 'custom' ? 2000 : +e.target.value)}><option value="0">{tr("不限数量（默认）")}</option><option value="100">{tr("100 项")}</option><option value="500">{tr("500 项")}</option><option value="1000">{tr("1000 项")}</option><option value="custom">{tr("自定义上限")}</option></select>{custom && <input aria-label={tr("自定义采集上限")} type="number" min="1" max="1000000" value={value} onChange={e => onChange(Math.max(1, +e.target.value))}/>}</div>;
}
export function PageSize({ value, onChange }: {
    value: number;
    onChange: (n: number) => void;
}) { return <label className="page-size">{tr("每页")}<select aria-label={tr("每页条目")} value={value} onChange={e => onChange(+e.target.value)}>{[50, 100, 200].map(n => <option key={n} value={n}>{n}{tr("条")}</option>)}</select></label>; }
export function useStored<T>(key: string, initial: T): [
    T,
    (value: T) => void
] {
    const [value, setValue] = React.useState<T>(() => readStored(key, initial));
    return [value, (next: T) => { setValue(next); writeStored(key, next); }];
}
