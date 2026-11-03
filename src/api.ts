import { tr,locale,serverText } from './i18n';
export type Photo = {
    id: string;
    width: number;
    height: number;
    size: number;
    created: string;
    published: string;
    tags: string;
    favorite: number;
    trash: number;
    note: string;
    color: string;
    author: string;
    reviewed: number;
    text_score: number | null;
    analysis_status: string;
    kind: 'image' | 'video' | 'gif';
    format: string;
    duration: number;
    parent: string;
    source_count: number;
    similarity?: number;
};
export type Source = {
    url: string;
    content: string;
    published: string;
    post_id: string;
    account: string;
    handle: string;
    alias: string;
};
export type Detail = Photo & {
    sources: Source[];
    albums: {
        id: string;
        name: string;
    }[];
    ocr_text: string;
};
export type Account = {
    country?:string;
    suggested_country?:string;
    country_language?:string;
    pinned_avatar?:string;
    id: string;
    handle: string;
    name: string;
    alias: string;
    note: string;
    categories: string;
    rating: number;
    created: string;
    last_checked: string;
    last_success?: string;
    last_published?: string;
    protected?: number;
    watermark: string;
    pending_top: string;
    schedule: string;
    next_run: string;
    auto_paused: number;
    retained: number;
    deleted: number;
    batches: number;
    images?: number;
    videos?: number;
    gifs?: number;
    storage?: number;
    task_id?: string;
    task_status?: string;
    last_imported?: number;
    last_added?: string;
    tasks?: Task[];
    availability?: string;
    availability_reason?: string;
    availability_checked?: string;
    avatar_path?: string;
    avatar_url?: string;
    custom_avatar?: string;
    avatar_fetched_url?: string;
};
export type Task = {
    id: string;
    url: string;
    mode: string;
    status: string;
    limit_count: number;
    imported: number;
    duplicates: number;
    excluded: number;
    scanned: number;
    message: string;
    created: string;
    updated: string;
    account: string;
    origin: string;
    retry_at: string;
    handle?: string;
    alias?: string;
    name?: string;
    options: string;
    failed: number;
    started: string;
    elapsed: number;
    downloaded_bytes: number;
    speed: number;
    result_json?: string;
    reason_code?: string;
};
export type Filters = {
    view?: string;
    account?: string;
    batch?: string;
    album?: string;
    q?: string;
    tag?: string;
    shape?: string;
    kind?: string;
    accountCategory?: string;
    accountRating?: string;
    sort?: string;
    from?: string;
    to?: string;
    dateField?: string;
    textFilter?: string;
    textThreshold?: number;
    ids?: string[];
};
export type Stats = {
    root: string;
    total: number;
    trash: number;
    revision: number;
    tags: string[];
    accountCategories: string[];
    albums: {
        id: string;
        name: string;
        count: number;
    }[];
    savedViews?: any[];
    pending: number;
    bytes: number;
    queueWaitingLogin?: boolean;
    queued?: number;
    freeBytes?: number;
    storage?: any;
    offline?: string;
    analysis: any;
    active: string | null;
};
declare global {
    interface Window {
        luma?: {
            call: (method: string, args?: Record<string, unknown>) => Promise<any>;
        };
    }
}
export async function api<T = any>(method: string, args: Record<string, unknown> = {}): Promise<T> { if (!window.luma)
    throw Error(tr("请从 Luma 桌面程序使用此功能")); try{return serverText(await window.luma.call(method,args))}catch(error){throw Error(tr(error instanceof Error?error.message:String(error)))}; }
export const date = (v: string) => v ? new Date(v).toLocaleString(locale(), { hour12: false }) : tr("尚无记录");
export const bytes = (v: number) => v >= 1073741824 ? (v / 1073741824).toFixed(2) + ' GB' : (v / 1048576).toFixed(1) + ' MB';
export const duration = (n: number) => `${Math.floor(n / 60)}:${Math.floor(n % 60).toString().padStart(2, '0')}`;
export const statuses: Record<string, string> = { queued: tr("等待中"), running: tr("采集中"), waiting: tr("等待重试"), paused: tr("已暂停"), partial: tr("待补齐"), completed: tr("已完成"), failed: tr("需要处理"), needs_login: tr("检查登录"), needs_access: tr("检查访问权限"), cancelled: tr("已取消"), blocked_account: tr("账号封禁") };
