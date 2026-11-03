const { tr } = require('./i18n.cjs');
const { BrowserWindow } = require('electron');
class BrowserCollector {
    constructor({ parent, rpc }) { this.parent = parent; this.rpc = rpc; this.window = null; }
    async start(args) {
        if (this.starting)
            throw Error(tr("浏览器补采正在打开，请稍候"));
        this.starting = true;
        try {
            return await this._start(args);
        }
        finally {
            this.starting = false;
        }
    }
    async _start(args) {
        if (this.window && !this.window.isDestroyed()) {
            this.window.show();
            throw Error(tr("已有浏览器补采窗口，请先结束当前补采"));
        }
        const source = await this.rpc('browserTask', args), account = source.account ? await this.rpc('account', { id: source.account }) : null;
        const task = await this.rpc('browserPrepare', args);
        let count = 0, closing = false;
        const requests = new Set(), pending = new Set();
        const window = this.window = new BrowserWindow({ width: 1100, height: 860, parent: this.parent, autoHideMenuBar: true, title: tr("Luma 浏览器补采 · 滚动查看媒体，关闭窗口结束"), webPreferences: { partition: 'persist:luma-x', contextIsolation: true, nodeIntegration: false, sandbox: true } });
        window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
        window.webContents.on('will-navigate', (event, value) => { try {
            const u = new URL(value);
            if (u.protocol !== 'https:' || !['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(u.hostname))
                event.preventDefault();
        }
        catch {
            event.preventDefault();
        } });
        const debuggerApi = window.webContents.debugger;
        try {
            debuggerApi.attach('1.3');
            await debuggerApi.sendCommand('Network.enable', { maxResourceBufferSize: 16 * 1024 * 1024, maxTotalBufferSize: 32 * 1024 * 1024 });
            debuggerApi.on('message', (_event, method, data) => {
                if (closing)
                    return;
                if (method === 'Network.responseReceived') {
                    try {
                        const u = new URL(data.response.url);
                        if (data.response.status === 200 && ['x.com', 'twitter.com'].includes(u.hostname) && /^\/i\/api\/graphql\//.test(u.pathname) && /UserMedia|UserTweets|TweetDetail/.test(u.pathname) && requests.size < 128)
                            requests.add(data.requestId);
                    }
                    catch { }
                }
                if (method === 'Network.loadingFailed')
                    requests.delete(data.requestId);
                if (method === 'Network.loadingFinished' && requests.delete(data.requestId)) {
                    const operation = (async () => {
                        const response = await debuggerApi.sendCommand('Network.getResponseBody', { requestId: data.requestId });
                        const body = response.base64Encoded ? Buffer.from(response.body, 'base64').toString('utf8') : response.body;
                        if (body.length > 12 * 1024 * 1024)
                            return;
                        const result = await this.rpc('browserCandidates', { id: task.id, owner: account?.handle || '', ownerId: account?.external_id || '', post: /\/status\/(\d+)/.exec(source.url)?.[1] || '', data: JSON.parse(body) });
                        count = result.total;
                        if (!window.isDestroyed())
                            window.setTitle(tr("Luma 浏览器补采 · 已发现 ") + count + tr(" 项 · 继续滚动，关闭窗口后选择下载"));
                    })().catch(() => { });
                    pending.add(operation);
                    operation.finally(() => pending.delete(operation));
                }
            });
            window.on('page-title-updated', event => event.preventDefault());
            window.once('closed', () => { closing = true; this.window = null; Promise.allSettled([...pending]).then(() => this.rpc('browserFinish', { id: task.id })).catch(() => { }); this.parent?.webContents.send('assistant-changed'); });
            await window.loadURL(source.url);
            return { id: task.id, message: tr("在打开的 X 页面中滚动加载媒体，关闭窗口后选择下载；仅采集当前可见且有权访问的媒体") };
        }
        catch (error) {
            if (!window.isDestroyed())
                window.destroy();
            await Promise.allSettled([...pending]);
            await this.rpc('browserFinish', { id: task.id }).catch(() => { });
            throw Error(tr("浏览器补采未开始，请检查网络并重试：") + error.message);
        }
    }
}
module.exports = { BrowserCollector };
