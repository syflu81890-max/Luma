const { tr } = require('./i18n.cjs');
const crypto = require('node:crypto');
// Public X web-client bearer, also used by the bundled gallery-dl extractor.
const WEB_BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';
function cookieSet(values) {
    const sorted = [...values].filter(c => !c.expirationDate || c.expirationDate > Date.now() / 1000).sort((a, b) => (b.path?.length || 0) - (a.path?.length || 0) || (b.expirationDate || 0) - (a.expirationDate || 0));
    const result = {};
    for (const c of sorted)
        if (['auth_token', 'ct0', 'twid'].includes(c.name) && result[c.name] === undefined)
            result[c.name] = c.value;
    return result;
}
class XSession {
    constructor(session) { this.session = session; this.cache = null; this.inflight = null; }
    async credentials() { const current = cookieSet(await this.session.cookies.get({ url: 'https://x.com/i/api/' })); if (current.auth_token)
        return current; return cookieSet(await this.session.cookies.get({ url: 'https://twitter.com/' })); }
    async cookies() { const c = await this.credentials(); if (c.auth_token && this.cache?.value.loggedIn === false && this.cache.fingerprint === crypto.createHash('sha256').update(c.auth_token).digest('hex'))
        return {}; return Object.fromEntries(Object.entries(c).filter(([key]) => key !== 'twid')); }
    async configureProxy(proxy = '') {
        proxy = String(proxy || '');
        if (this.proxy === proxy)
            return;
        if (proxy) {
            const u = new URL(proxy);
            if (!['http:', 'https:', 'socks4:', 'socks5:', 'socks5h:'].includes(u.protocol) || !u.hostname)
                throw Error(tr("代理格式无效，请使用 http:// 或 socks5:// 地址"));
        }
        await this.session.setProxy(proxy ? { mode: 'fixed_servers', proxyRules: proxy.replace(/^socks5h:/, 'socks5:') } : { mode: 'system' });
        this.proxy = proxy;
        this.cache = null;
    }
    async info(refresh = false) {
        const c = await this.credentials();
        if (!c.auth_token)
            return { loggedIn: false, verified: false, handle: '', message: tr("未检测到 X 登录，请在软件中登录") };
        const fingerprint = crypto.createHash('sha256').update(c.auth_token).digest('hex');
        if (!refresh && this.cache?.fingerprint === fingerprint && Date.now() - this.cache.time < 300000)
            return this.cache.value;
        if (this.inflight)
            return this.inflight;
        this.inflight = (async () => {
            let value = { loggedIn: true, verified: false, handle: '', message: tr("已检测到登录会话，身份验证暂未完成；请检查网络后重试") };
            try {
                const response = await this.session.fetch('https://x.com/i/api/1.1/account/settings.json', { credentials: 'include', headers: { authorization: 'Bearer ' + WEB_BEARER, 'x-csrf-token': c.ct0 || '', 'x-twitter-auth-type': 'OAuth2Session', 'x-twitter-active-user': 'yes' }, signal: AbortSignal.timeout(20000) });
                if (response.ok) {
                    const data = await response.json();
                    if (/^[A-Za-z0-9_]{1,15}$/.test(data.screen_name || ''))
                        value = { loggedIn: true, verified: true, handle: data.screen_name, message: tr("已验证当前 X 登录身份") };
                }
                else if (response.status === 401)
                    value = { loggedIn: false, verified: false, handle: '', message: tr("X 登录已失效，请重新登录") };
                else
                    value.message = response.status === 429 ? tr("身份验证请求受限，请稍后再试") : tr("登录身份尚未确认（平台返回 ") + response.status + tr("），请打开 X 核对");
            }
            catch { }
            this.cache = { fingerprint, time: Date.now(), value };
            return value;
        })().finally(() => { this.inflight = null; });
        return this.inflight;
    }
}
module.exports = { XSession, cookieSet };
