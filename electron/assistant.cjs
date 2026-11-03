const { tr } = require('./i18n.cjs');
// Local control bridge. Never expose the renderer's unrestricted IPC transport.
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const READS = new Set(['stats', 'list', 'detail', 'files', 'accounts', 'account', 'taskPage', 'storageStatus', 'libraryLocation', 'aiSearch', 'assistantDuplicates', 'assistantFolder', 'assistantJob', 'assistantJobs', 'assistantPlanInfo', 'dashboard', 'collections', 'accountHistory', 'accountHealthStatus', 'similarStatus', 'similarPage']);
const WRITES = new Set(['assistantPlan', 'assistantApply', 'assistantUndo', 'assistantEditPrepare', 'assistantEditCommit', 'saveAccount', 'album', 'addTask', 'taskAction', 'organizeStorage', 'collectionAction', 'collectAll', 'accountHealthCheck', 'similarScan', 'similarPlan', 'similarCancel']);
const METHODS = [...READS, ...WRITES];
function atomic(file, data) { const temp = file + '.' + crypto.randomUUID() + '.pending'; fs.writeFileSync(temp, JSON.stringify(data, null, 2), { mode: 0o600 }); fs.renameSync(temp, file); }
class LocalAssistant {
    constructor({ profile, call, version = '0.4.0' }) {
        this.profile = profile;
        this.call = call;
        this.version = version;
        this.server = null;
        this.error = '';
        this.configFile = path.join(profile, 'assistant-settings.json');
        this.connectionFile = path.join(profile, 'assistant-connection.json');
        this.config = { enabled: false, port: 48120 };
        this.token = crypto.randomBytes(32).toString('hex');
        try {
            const saved = JSON.parse(fs.readFileSync(this.configFile, 'utf8'));
            this.config = { enabled: saved.enabled === true, port: Number.isInteger(saved.port) && saved.port >= 0 && saved.port <= 65535 ? saved.port : 48120 };
        }
        catch { }
    }
    status() { const address = this.server?.address(); return { ...this.config, running: !!address, url: address ? `http://127.0.0.1:${address.port}` : '', connectionFile: this.connectionFile, error: this.error, version: this.version }; }
    persistConnection() { const s = this.status(); atomic(this.connectionFile, { version: 1, app: 'Luma', pid: process.pid, running: s.running, url: s.url, token: s.running ? this.token : '', transport: 'HTTP JSON', rpc: '/v1/rpc', updated: new Date().toISOString() }); }
    async start() {
        this.error = '';
        if (!this.config.enabled) {
            this.persistConnection();
            return this.status();
        }
        const server = http.createServer((req, res) => this.handle(req, res));
        server.requestTimeout = 15000;
        server.headersTimeout = 10000;
        server.keepAliveTimeout = 1000;
        server.maxHeadersCount = 30;
        try {
            await new Promise((resolve, reject) => { server.once('error', reject); server.listen(this.config.port, '127.0.0.1', resolve); });
            this.server = server;
            server.on('error', e => { this.error = e.message; });
            this.persistConnection();
        }
        catch (e) {
            server.close();
            this.error = e.code === 'EADDRINUSE' ? tr("端口已被占用，请修改端口或选择自动分配（0）") : e.message;
            this.persistConnection();
        }
        return this.status();
    }
    async close() { const s = this.server; this.server = null; this.persistConnection(); if (s) {
        await new Promise(resolve => { s.close(resolve); s.closeIdleConnections(); });
    } }
    configure(a = {}) { const next = (this.changes || Promise.resolve()).catch(() => { }).then(() => this.reconfigure(a)); this.changes = next; return next; }
    async reconfigure(a = {}) {
        const port = a.port === undefined ? this.config.port : a.port;
        if (!Number.isInteger(port) || port < 0 || port > 65535 || port > 0 && port < 1024)
            throw Error(tr("端口为 0（自动）或 1024–65535"));
        const next = { enabled: a.enabled === undefined ? this.config.enabled : !!a.enabled, port };
        if (next.enabled !== this.config.enabled || port !== this.config.port || a.rotate) {
            await this.close();
            this.config = next;
            this.token = crypto.randomBytes(32).toString('hex');
            atomic(this.configFile, this.config);
            return this.start();
        }
        if (!this.server && this.config.enabled)
            return this.start();
        return this.status();
    }
    async handle(req, res) {
        const reply = (status, data) => { if (!res.destroyed) {
            res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Connection': 'close' });
            res.end(JSON.stringify(data));
        } };
        try {
            const port = this.server?.address()?.port;
            if (![`127.0.0.1:${port}`, `localhost:${port}`].includes(req.headers.host))
                return reply(403, { error: 'Invalid Host' });
            // Browser pages cannot access the bridge, including requests from localhost origins.
            if (req.headers.origin || req.headers['sec-fetch-site'])
                return reply(403, { error: 'Browser origins are not allowed' });
            const supplied = String(req.headers.authorization || ''), expected = 'Bearer ' + this.token;
            if (Buffer.byteLength(supplied) !== Buffer.byteLength(expected) || !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected)))
                return reply(401, { error: 'Local bearer token required' });
            if (req.method === 'GET' && req.url === '/v1/status')
                return reply(200, { app: 'Luma', version: this.version, localOnly: true });
            if (req.method === 'GET' && req.url === '/v1/capabilities')
                return reply(200, { protocol: 1, methods: METHODS, workflow: { manage: 'assistantPlan → assistantPlanInfo → assistantApply', edit: 'assistantEditPrepare → external image editing tool → assistantEditCommit' }, limitations: ['No image generation inside Luma', 'No shell, cookies, permanent deletion, system power or library switching'] });
            if (req.method !== 'POST' || req.url !== '/v1/rpc')
                return reply(404, { error: 'Unknown endpoint' });
            if (!String(req.headers['content-type'] || '').startsWith('application/json'))
                return reply(415, { error: 'application/json required' });
            let size = 0;
            const chunks = [];
            for await (const chunk of req) {
                size += chunk.length;
                if (size > 1048576) {
                    reply(413, { error: 'Request exceeds 1 MiB' });
                    req.resume();
                    return;
                }
                chunks.push(chunk);
            }
            let data;
            try {
                data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
            }
            catch {
                return reply(400, { error: 'Invalid JSON' });
            }
            if (!data || !METHODS.includes(data.method) || data.args !== undefined && (!data.args || Array.isArray(data.args) || typeof data.args !== 'object'))
                return reply(400, { error: 'Unsupported method or arguments' });
            const result = await this.call(data.method, data.args || {}, !READS.has(data.method));
            reply(200, { result });
        }
        catch (e) {
            reply(400, { error: String(e.message || e) });
        }
    }
}
module.exports = { LocalAssistant, READS, METHODS };
