const { tr,setLanguage } = require('./i18n.cjs');
const { app, BrowserWindow, ipcMain, dialog, session, shell, clipboard, ClipboardItem, nativeImage, Menu, Tray, protocol, net, powerMonitor, Notification } = require('electron');
const { spawn, spawnSync, execFile } = require('node:child_process');
const { prepareProfile } = require('./profile.cjs');
const { CompletionController } = require('./completion.cjs');
const { LocalAssistant } = require('./assistant.cjs');
const { Workspaces } = require('./workspaces.cjs');
const { XSession } = require('./x-session.cjs');
const { BrowserCollector } = require('./browser-collector.cjs');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const { pathToFileURL } = require('node:url');
const { Readable } = require('node:stream');
let backend, win, tray, backendReady = false, serial = 0, backendError = '', quitting = false, ticking = false, preferences = {}, libraryRoot = '';
const pending = new Map();
protocol.registerSchemesAsPrivileged([{ scheme: 'luma', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }]);
let completion, assistant, workspaces, xSession, browserCollector, powerExecuting = false, ipcBusy = 0, ipcGeneration = 0, libraryTransition = null;
let librarySwitchState = { status: 'idle', phase: '' };
function switchEvent(state) { librarySwitchState = state; if (win && !win.isDestroyed())
    win.webContents.send('library-switch', state); }
async function switchLibrary(args) {
    if (libraryTransition)
        throw Error(tr("已有资料库切换正在进行，请等待或取消"));
    libraryTransition = {};
    switchEvent({ status: 'running', phase: 'checking', started: Date.now() / 1000 });
    let polling = false;
    const timer = setInterval(async () => { if (polling)
        return; polling = true; try {
        const state = await rpc('switchStatus', {}, 2500);
        if (libraryTransition && state.status === 'running')
            switchEvent(state);
    }
    catch { }
    finally {
        polling = false;
    } }, 400);
    try {
        return await rpc('switchLibrary', args, 3600000);
    }
    finally {
        clearInterval(timer);
        libraryTransition = null;
        switchEvent({ status: 'idle', phase: '' });
    }
}
// Tests explicitly bind an isolated profile before requiring this module.
if (process.env.LUMA_TEST_ROOT) {
    const isolated = path.resolve(process.env.LUMA_TEST_ROOT);
    fs.mkdirSync(isolated, { recursive: true });
    app.setPath('userData', isolated);
    app.setPath('sessionData', isolated);
}
const usualProfile = path.join(app.getPath('appData'), 'luma-x-library');
let startupProfile;
if (!process.env.LUMA_TEST_ROOT && path.resolve(app.getPath('userData')).toLowerCase() === path.resolve(usualProfile).toLowerCase()) {
    try {
        const helper = (args, timeout = 30000) => {
            const exe = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'luma-backend.exe') : process.env.LUMA_PYTHON || path.join(__dirname, '../.venv/Scripts/python.exe');
            const argv = app.isPackaged ? args : [path.join(__dirname, '../backend/app.py'), ...args];
            const r = spawnSync(exe, argv, { encoding: 'utf8', windowsHide: true, timeout, maxBuffer: 4 * 1024 * 1024 });
            if (r.error || r.status !== 0)
                throw Error(r.error?.message || String(r.stderr).slice(-600) || tr("旧配置检查失败"));
            return JSON.parse(r.stdout);
        };
        startupProfile = prepareProfile({ current: usualProfile, home: app.getPath('home'), inspect: profiles => helper(['--inspect-profiles', JSON.stringify(profiles)]), snapshot: (from, to) => helper(['--snapshot-profile-library', from, to], 300000) });
        app.setPath('userData', startupProfile.profile);
        app.setPath('sessionData', startupProfile.profile);
    }
    catch (e) {
        dialog.showErrorBox(tr("Luma · 配置恢复未完成"), e.message + tr("\n原资料库和任务均未被覆盖。"));
        app.exit(1);
        throw e;
    }
}
const primary = app.requestSingleInstanceLock();
if (!primary)
    app.quit();
function prefsFile() { return path.join(app.getPath('userData'), 'desktop-settings.json'); }
async function copyOriginalImage(file) { const image = nativeImage.createFromPath(file); if (image.isEmpty())
    throw Error(tr("该媒体请使用复制文件功能")); await clipboard.write([new ClipboardItem({ 'image/png': new Blob([image.toPNG()], { type: 'image/png' }) })]); }
function rpc(method, args = {}, timeout = backendReady ? 120000 : 600000) {
    return new Promise((resolve, reject) => {
        if (!backend || backend.exitCode !== null || backend.killed)
            return reject(new Error(backendError || tr("后台已退出，请重新启动软件")));
        const id = ++serial, timer = setTimeout(() => { pending.delete(id); reject(new Error(tr("后台处理超时；任务可能仍在执行，请查看状态"))); }, timeout);
        pending.set(id, { resolve, reject, timer });
        backend.stdin.write(JSON.stringify({ id, method, args }) + '\n', e => { if (e) {
            clearTimeout(timer);
            pending.delete(id);
            reject(e);
        } });
    });
}
function startBackend() {
    backendReady = false;
    const root = process.env.LUMA_TEST_ROOT || app.getPath('userData');
    backend = app.isPackaged ? spawn(path.join(process.resourcesPath, 'backend', 'luma-backend.exe'), ['--root', root], { windowsHide: true }) : spawn(process.env.LUMA_PYTHON || path.join(__dirname, '../.venv/Scripts/python.exe'), [path.join(__dirname, '../backend/app.py'), '--root', root], { windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' } });
    readline.createInterface({ input: backend.stdout }).on('line', line => { try {
        const r = JSON.parse(line), p = pending.get(r.id);
        if (p) {
            backendReady = true;
            pending.delete(r.id);
            clearTimeout(p.timer);
            r.error ? p.reject(new Error(r.error)) : p.resolve(r.result);
        }
    }
    catch { } });
    const rejectAll = e => { backendError = String(e.message || e); for (const p of pending.values()) {
        clearTimeout(p.timer);
        p.reject(new Error(backendError));
    } pending.clear(); };
    backend.on('error', rejectAll);
    backend.on('exit', () => rejectAll(new Error(tr("采集后台已退出，请重启软件；已入库内容保留"))));
    backend.stderr.on('data', data => { backendError = String(data).slice(-800); });
}
async function cookies() {
    return xSession.cookies();
}
const taskStates = new Map();
let notificationsReady = false;
async function tick() {
    if (process.env.LUMA_RECOVERY_VERIFY === '1' || ticking || quitting || libraryTransition)
        return;
    ticking = true;
    try {
        await rpc('scheduleTick', { cookies: await cookies() });
        const tasks = await rpc('tasks');
        for (const task of tasks) {
            const previous = taskStates.get(task.id), meaningful = (['completed', 'partial'].includes(task.status) && task.imported > 0) || ['failed', 'needs_login'].includes(task.status);
            if (notificationsReady && previous !== task.status && task.origin === 'schedule' && meaningful && preferences.notifications && Notification.isSupported())
                new Notification({ title: 'Luma', body: ['completed', 'partial'].includes(task.status) ? tr("定时采集新增 {0} 项{1}", [task.imported, task.status === 'partial' ? tr("，仍有内容待补齐") : '']) : tr("定时采集需要检查，请查看任务页。") }).show();
            taskStates.set(task.id, task.status);
        }
        notificationsReady = true;
    }
    catch { }
    finally {
        ticking = false;
    }
}
function stopBackendForPower() {
    return new Promise(async (resolve, reject) => {
        try {
            if (!backend || backend.exitCode !== null)
                throw Error(tr("后台已退出，请重启软件后重新设置"));
            const child = backend;
            await rpc('shutdown', {}, 10000);
            const timer = setTimeout(() => reject(Error(tr("后台尚未安全退出，未发送系统动作，请重启 Luma"))), 30000);
            const finish = () => { clearTimeout(timer); backend = null; resolve(); };
            child.once('exit', finish);
            child.stdin.end();
            if (child.exitCode !== null) {
                child.removeListener('exit', finish);
                finish();
            }
        }
        catch (e) {
            reject(e);
        }
    });
}
function executePower(action) {
    return new Promise((resolve, reject) => {
        if (process.env.LUMA_POWER_DRY_RUN === '1') {
            resolve();
            return;
        }
        const executable = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'luma-backend.exe') : process.env.LUMA_PYTHON || path.join(__dirname, '../.venv/Scripts/python.exe');
        const args = app.isPackaged ? ['--power', action] : [path.join(__dirname, '../backend/app.py'), '--power', action];
        execFile(executable, args, { windowsHide: true }, (error, _stdout, stderr) => error ? reject(Error(String(stderr || error.message).slice(-300))) : resolve());
    });
}
function updateTray() { if (tray)
    tray.setContextMenu(Menu.buildFromTemplate([{ label: tr("打开 Luma"), click: () => win.show() }, { label: tr("检查定时任务"), click: () => tick() }, { label: tr("取消完成后动作"), enabled: !!completion && ['waiting', 'countdown', 'preparing'].includes(completion.state.phase), click: () => completion.cancel().catch(() => { }) }, { type: 'separator' }, { label: tr("退出"), click: () => { quitting = true; app.quit(); } }])); }
async function chooseDirectory() { const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] }); return r.canceled ? null : r.filePaths[0]; }
function applyPrefs() { if (win) {
    win.webContents.setZoomFactor(Math.max(.8, Math.min(2, Number(preferences.zoom) || 1)));
    win.webContents.send('preferences', preferences);
} if (Object.hasOwn(preferences, 'startAtLogin'))
    app.setLoginItemSettings({ openAtLogin: !!preferences.startAtLogin, args: ['--background'] }); }
async function contextMenu(args) {
    const ids = args.ids || [], id = args.id || ids[0], files = await rpc('files', { ids: [id] });
    if (!files.length)
        throw Error(tr("原文件不可用，请检查资料库位置"));
    const detail = await rpc('detail', { id });
    const sourceAccounts=await rpc('mediaAccounts',{id});
    return new Promise(resolve => {
        let action = '';
        const act = (name, fn) => async () => { action = name; try {
            await fn();
            resolve(name);
        }
        catch (e) {
            resolve(tr("错误：") + e.message);
        } };
        const items = [{ label: detail.kind === 'gif' ? tr("复制 GIF 首帧") : tr("复制图片（原图）"), enabled: detail.kind === 'image' || detail.kind === 'gif' && detail.format === 'gif', click: act(tr("已复制图片"), () => copyOriginalImage(files[0])) }, { label: tr("复制文件{0}", [ids.length > 1 ? '（' + ids.length + tr(" 项）") : '']), click: act(tr("已复制文件"), () => rpc('copyFiles', { ids })) }, { type: 'separator' }, { label: tr("复制原帖链接"), enabled: detail.sources.length > 0, click: act(tr("已复制链接"), () => clipboard.writeText(detail.sources.map(s => s.url).join('\n'))) }, { label: tr("复制推文文字"), enabled: detail.sources.some(s => s.content), click: act(tr("已复制推文"), () => clipboard.writeText(detail.sources.map(s => s.content).filter(Boolean).join('\n\n'))) }, { type: 'separator' }, { label: tr("打开文件所在位置"), click: act(tr("已打开文件位置"), () => shell.showItemInFolder(files[0])) }, { label: detail.kind === 'video' ? tr("使用系统播放器打开") : tr("编辑副本（保留原图）"), click: act(tr("已打开"), async () => {
                    if (detail.kind === 'video')
                        return shell.openPath(files[0]);
                    const directory = path.join(libraryRoot || (await rpc('libraryLocation')).path, 'edits');
                    fs.mkdirSync(directory, { recursive: true });
                    const copy = path.join(directory, Date.now() + '-' + path.basename(files[0]));
                    await fs.promises.copyFile(files[0], copy);
                    if (preferences.editor)
                        spawn(preferences.editor, [copy], { windowsHide: true, detached: true, stdio: 'ignore' }).unref();
                    else
                        await shell.openPath(copy);
                }) }];
        if(sourceAccounts.length){items.unshift({label:tr('进入软件内账号主页'),submenu:sourceAccounts.map(account=>({label:(account.alias||account.name||account.handle)+' (@'+account.handle+')',click:act(tr('打开图库'),()=>{win.webContents.send('open-account',{id:account.id})})}))},{type:'separator'})}
        const menu = Menu.buildFromTemplate(items);
        menu.once('menu-will-close', () => setTimeout(() => { if (!action)
            resolve(''); }, 100));
        menu.popup({ window: win });
    });
}
function trayIcon() { const pixels = Buffer.alloc(24 * 24 * 4); for (let y = 0; y < 24; y++)
    for (let x = 0; x < 24; x++) {
        const i = (y * 24 + x) * 4;
        pixels[i] = 230;
        pixels[i + 1] = 120;
        pixels[i + 2] = 55;
        pixels[i + 3] = 255;
        if ((x === 6 || y === 17) && x > 4 && y > 5) {
            pixels[i] = 255;
            pixels[i + 1] = 255;
            pixels[i + 2] = 255;
        }
    } return nativeImage.createFromBitmap(pixels, { width: 24, height: 24 }); }
if (primary)
    app.whenReady().then(async () => {
        try {
            preferences = JSON.parse(fs.readFileSync(prefsFile(), 'utf8'));
        }
        catch { }
        setLanguage(preferences.language,app.getLocale());workspaces = new Workspaces(app.getPath('userData'));
        xSession = new XSession(session.fromPartition('persist:luma-x'));
        startBackend();
        assistant = new LocalAssistant({ profile: app.getPath('userData'), version: app.getVersion(), call: async (method, args, writes) => {
                if (quitting || powerExecuting)
                    throw Error(tr("软件正在退出或执行完成后动作"));
                if (writes && completion?.state.phase === 'preparing')
                    throw Error(tr("正在安全保存，请先取消本次完成后动作"));
                if (writes) {
                    ipcBusy++;
                    ipcGeneration++;
                }
                try {
                    if (['addTask', 'taskAction', 'collectAll', 'accountHealthCheck'].includes(method))
                        args = { ...args, cookies: await cookies() };
                    const result = await rpc(method, args, 300000);
                    if (writes && win && !win.isDestroyed())
                        win.webContents.send('assistant-changed');
                    return result;
                }
                finally {
                    if (writes)
                        ipcBusy--;
                }
            } });
        await assistant.start();
        completion = new CompletionController({ backend: async (a) => { if (a.action === 'prepare' && ipcBusy)
                return { ready: false }; const state = await rpc('completion', a, 5000); return { ...state, ready: state.ready && !ipcBusy, generation: String(state.generation) + ':' + ipcGeneration }; }, execute: async (action) => { powerExecuting = true; try {
                await stopBackendForPower();
                if (completion.cancelRequested)
                    throw Error(tr("已取消系统动作；后台已安全退出，请重新启动 Luma"));
                await executePower(action);
                quitting = true;
                app.quit();
            }
            finally {
                powerExecuting = false;
            } }, publish: state => { if (win && !win.isDestroyed()) {
                win.webContents.send('completion', state);
                if (state.phase === 'countdown' && state.remaining === 60) {
                    if (win.isMinimized())
                        win.restore();
                    win.show();
                    if (Notification.isSupported())
                        new Notification({ title: tr("Luma · 完成后动作"), body: state.message }).show();
                }
            } updateTray(); } });
        setInterval(() => completion.tick(), 1000).unref();
        protocol.handle('luma', async (request) => {
            try {
                const u = new URL(request.url), id = u.pathname.slice(1);
                if (u.hostname !== 'media' || !/^[a-f0-9]{64}$/.test(id))
                    return new Response('Not found', { status: 404 });
                const files = await rpc('files', { ids: [id] });
                if (!files.length)
                    return new Response('Missing original', { status: 404 });
                const file = files[0], size = (await fs.promises.stat(file)).size, mimes = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska' };
                const headers = { 'Content-Type': mimes[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Range' };
                if (request.method === 'OPTIONS')
                    return new Response(null, { status: 204, headers });
                const range = request.headers.get('Range');
                let start = 0, end = size - 1, status = 200;
                if (range) {
                    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
                    if (!match)
                        return new Response(null, { status: 416, headers: { ...headers, 'Content-Range': `bytes */${size}` } });
                    start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
                    end = match[1] && match[2] ? Math.min(size - 1, Number(match[2])) : size - 1;
                    if (start > end || start >= size)
                        return new Response(null, { status: 416, headers: { ...headers, 'Content-Range': `bytes */${size}` } });
                    status = 206;
                    headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
                }
                headers['Content-Length'] = String(end - start + 1);
                return new Response(request.method === 'HEAD' ? null : Readable.toWeb(fs.createReadStream(file, { start, end })), { status, headers });
            }
            catch (e) {
                console.error('Media protocol:', e.message);
                return new Response('Media unavailable', { status: 503 });
            }
        });
        ipcMain.handle('api', async (event, method, args = {}) => {
            if (event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame)
                throw Error(tr("无效调用来源"));
            if (method === 'windowMinimize') {
                win.minimize();
                return true;
            }
            if (method === 'librarySwitchStatus')
                return librarySwitchState;
            if (method === 'cancelLibrarySwitch'){if(libraryTransition)libraryTransition.cancelRequested=true;return rpc('cancelSwitch', {}, 3000)}
            if (libraryTransition)
                throw Error(tr("资料库正在切换，请稍候；可查看切换进度或取消"));
            if (method === 'projectLink') {
                const routes = { issues: 'https://github.com/syflu81890-max/Luma/issues', bug: 'https://github.com/syflu81890-max/Luma/issues/new?template=bug_report.yml', feature: 'https://github.com/syflu81890-max/Luma/issues/new?template=feature_request.yml', source: 'https://github.com/syflu81890-max/Luma', license: 'https://github.com/syflu81890-max/Luma/blob/main/LICENSE' };
                if (!Object.hasOwn(routes, args.page))
                    throw Error(tr("未知项目页面"));
                return shell.openExternal(routes[args.page]);
            }
            if(method==='reloadWindow'){setTimeout(()=>{if(win&&!win.isDestroyed())win.webContents.reload()},50);return true}
            if (method === 'assistantStatus')
                return assistant.status();
            if (method === 'assistantConfigure')
                return assistant.configure(args);
            if (method === 'assistantCopyConnection') {
                const s = assistant.status();
                clipboard.writeText(s.connectionFile);
                return true;
            }
            if (method === 'completionState')
                return completion.current();
            if (method === 'completionPlan') {
                return args.action === 'none' ? completion.cancel() : completion.arm(args.action, !!args.waitAnalysis);
            }
            if (powerExecuting)
                throw Error(tr("正在保存并执行完成后动作，请稍候"));
            const readOnly = ['stats', 'list', 'selectIds', 'detail', 'image', 'files', 'copyFiles', 'accounts', 'accountIds', 'account', 'avatar', 'tasks', 'taskPage', 'taskIds', 'candidateIds', 'candidatePage', 'candidates', 'candidateImage', 'settings', 'similar', 'check', 'aiSearch', 'libraryLocation', 'loginStatus', 'storageStatus', 'dashboard', 'accountChoices','notePresets','accountRemovePlan','mediaAccounts','collections', 'accountHistory', 'historyAvatar', 'accountHealthStatus', 'similarStatus', 'similarPage', 'workspaceInfo', 'savedViews', 'backgroundStatus', 'followingStatus', 'followingPage'];
            const writes = method === 'desktopSettings' ? !!args.save : !readOnly.includes(method);
            if (writes && completion.state.phase === 'preparing')
                throw Error(tr("正在安全保存，请先取消本次完成后动作"));
            if (writes) {
                ipcBusy++;
                ipcGeneration++;
            }
            try {
                if (method === 'workspaceInfo') {
                    const location = await rpc('libraryLocation');
                    libraryRoot = location.path;
                    const first = !workspaces.items.length, row = workspaces.track(libraryRoot);
                    const settings = await rpc('settings');
                    let networkWarning = '';
                    try {
                        await xSession.configureProxy(settings.proxy || '');
                    }
                    catch (error) {
                        networkWarning = tr("应用内浏览器代理需要检查：") + error.message;
                    }
                    if (first) {
                        row.appearance = { theme: preferences.theme || 'light', zoom: preferences.zoom || 1, fontScale: preferences.fontScale || 1 };
                        workspaces.write();
                    }
                    return { ...workspaces.info(libraryRoot), networkWarning };
                }
                if (method === 'workspaceSave')
                    return workspaces.save((await rpc('libraryLocation')).path, args);
                if (method === 'workspaceLogo') {
                    const root = (await rpc('libraryLocation')).path, row = workspaces.track(root);
                    if (args.reset)
                        return workspaces.save(root, { logo: '' });
                    const picked = await dialog.showOpenDialog(win, { properties: ['openFile'], filters: [{ name: tr("空间标识"), extensions: ['png', 'jpg', 'jpeg', 'webp'] }] });
                    if (picked.canceled)
                        return workspaces.info(root);
                    const image = nativeImage.createFromPath(picked.filePaths[0]);
                    if (image.isEmpty())
                        throw Error(tr("这张图片无法读取，请换用 PNG 或 JPEG"));
                    const directory = path.join(app.getPath('userData'), 'workspace-assets');
                    fs.mkdirSync(directory, { recursive: true });
                    const file = path.join(directory, row.id + '.png');
                    await fs.promises.writeFile(file, image.resize({ width: 160, height: 160, quality: 'best' }).toPNG());
                    return workspaces.save(root, { logo: file });
                }
                if (method === 'workspaceSelect') {
                    const row = workspaces.get(args.id), current = (await rpc('libraryLocation')).path;
                    if (path.resolve(row.path).toLowerCase() !== path.resolve(current).toLowerCase()) {
                        const result = await switchLibrary({ path: row.path, mode: 'switch' });
                        libraryRoot = result.path;
                    }
                    preferences = { ...preferences, theme: row.appearance?.theme || 'light', zoom: row.appearance?.zoom || 1, fontScale: row.appearance?.fontScale || 1 };
                    fs.writeFileSync(prefsFile(), JSON.stringify(preferences));
                    applyPrefs();
                    return workspaces.info(libraryRoot || current);
                }
                if (method === 'browserCollect')
                    return browserCollector.start(args);
                if (method === 'desktopSettings') {
                    if (args.save) {
                        preferences = { ...preferences, ...args.save };setLanguage(preferences.language,app.getLocale());
                        fs.writeFileSync(prefsFile(), JSON.stringify(preferences));
                        const row = workspaces.track((await rpc('libraryLocation')).path);
                        row.appearance = { theme: preferences.theme || 'light', zoom: preferences.zoom || 1, fontScale: preferences.fontScale || 1 };
                        workspaces.write();
                        applyPrefs();
                    }
                    return { ...preferences, startAtLogin: app.getLoginItemSettings().openAtLogin };
                }
                if (method === 'refreshSession') {
                    const result = await xSession.info(true);
                    await tick();
                    return result;
                }
                if (method === 'profileInfo')
                    return { profile: app.getPath('userData'), recovered: !!startupProfile?.migrated };
                if (method === 'loginStatus')
                    return xSession.info(!!args.refresh);
                if (method === 'login') {
                    const w = new BrowserWindow({ width: 1060, height: 800, parent: win, autoHideMenuBar: true, webPreferences: { partition: 'persist:luma-x', nodeIntegration: false, contextIsolation: true, sandbox: true } });
                    w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
                    w.webContents.on('will-navigate', (e, url) => { const u = new URL(url); if (u.protocol !== 'https:' || !['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'].includes(u.hostname))
                        e.preventDefault(); });
                    w.on('closed', () => { xSession.cache = null; tick(); });
                    await w.loadURL(args.home ? 'https://x.com/home' : 'https://x.com/i/flow/login');
                    return true;
                }
                if (method === 'contextMenu')
                    return contextMenu(args);
                if (method === 'copyImage') {
                    const files = await rpc('files', { ids: [args.id] });
                    if (!files.length)
                        throw Error(tr("原图不可用"));
                    await copyOriginalImage(files[0]);
                    return true;
                }
                if (method === 'openSource') {
                    const u = new URL(args.url);
                    if (u.protocol !== 'https:' || !['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'].includes(u.hostname))
                        throw Error(tr("无效来源"));
                    return shell.openExternal(u.href);
                }
                if (method === 'openMediaRoot' || method === 'openAccountFolder')
                    return shell.openPath(await rpc('storageFolder', method === 'openAccountFolder' ? { id: args.id } : {}));
                if (method === 'openData') {
                    const location = await rpc('libraryLocation');
                    return shell.openPath(location.path);
                }
                if (method === 'openMedia') {
                    const files = await rpc('files', { ids: [args.id] });
                    if (files[0])
                        return shell.openPath(files[0]);
                    throw Error(tr("原文件不可用"));
                }
                if (['importDialog', 'importEditDialog'].includes(method)) {
                    const r = await dialog.showOpenDialog(win, { properties: ['openFile', 'multiSelections'], filters: [{ name: tr("图片、视频与 GIF"), extensions: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'mp4', 'webm', 'mov', 'mkv', 'm4v'] }] });
                    return r.canceled ? null : rpc(method === 'importDialog' ? 'import' : 'importEdit', { paths: r.filePaths, parent: args.parent }, 1800000);
                }
                if (method === 'folderDialog') {
                    const dir = await chooseDirectory();
                    return dir ? rpc('importFolder', { path: dir }, 1800000) : null;
                }
                if (method === 'exportDialog') {
                    const dir = await chooseDirectory();
                    return dir ? rpc('export', { ...args, path: dir }, 1800000) : null;
                }
                if (method === 'avatarDialog') {
                    const r = await dialog.showOpenDialog(win, { properties: ['openFile'], filters: [{ name: tr("头像"), extensions: ['jpg', 'jpeg', 'png', 'webp'] }] });
                    return r.canceled ? null : rpc('customAvatar', { id: args.id, path: r.filePaths[0] });
                }
                if (method === 'editorDialog') {
                    const r = await dialog.showOpenDialog(win, { properties: ['openFile'], filters: [{ name: tr("编辑器"), extensions: ['exe'] }] });
                    if (!r.canceled) {
                        preferences.editor = r.filePaths[0];
                        fs.writeFileSync(prefsFile(), JSON.stringify(preferences));
                    }
                    return preferences.editor || '';
                }
                if (method === 'libraryDialog') {
                    const dir = await chooseDirectory();
                    if (!dir)
                        return null;
                    const target = args.mode === 'migrate' ? path.join(dir, 'Luma-Library-' + Date.now()) : dir;
                    const previous = (await rpc('libraryLocation')).path;
                    const result = await switchLibrary({ mode: args.mode, path: target });
                    libraryRoot = result.path;
                    if (args.mode === 'migrate') {
                        const row = workspaces.track(previous);
                        row.path = libraryRoot;
                        workspaces.write();
                    }
                    else
                        workspaces.track(libraryRoot);
                    return result;
                }
                if (method === 'backupDialog') {
                    const dir = await chooseDirectory();
                    return dir ? rpc('backup', { path: path.join(dir, 'Luma-Backup-' + Date.now()) }, 3600000) : null;
                }
                if (['addTask', 'taskAction', 'accountBatch', 'taskBatch', 'collectAll', 'accountHealthCheck', 'followingStart', 'followingImport'].includes(method))
                    args = { ...args, cookies: await cookies() };
                const allowed = ['stats', 'list', 'selectIds', 'detail', 'image', 'update', 'undo', 'purge', 'accounts', 'accountIds', 'accountBatch', 'taskPage', 'taskIds', 'taskBatch', 'candidateIds', 'candidatePage', 'account', 'saveAccount', 'addAccount', 'schedule', 'avatar', 'refreshAvatar', 'resetAccount', 'tasks', 'addTask', 'taskAction', 'candidates', 'candidateImage', 'album', 'storageStatus', 'organizeStorage', 'settings', 'saveSettings', 'similar', 'check', 'clearCache', 'analysis', 'aiSearch', 'libraryLocation', 'copyFiles', 'dashboard', 'accountChoices','notePresets','accountRemovePlan','mediaAccounts','collections', 'notePresetUse','accountRemove','accountRegion','collectionAction', 'accountHistory', 'historyAvatar', 'accountHealthStatus', 'accountHealthCheck', 'collectAll', 'similarIgnore','similarScan', 'similarStatus', 'similarPage', 'similarPlan', 'similarCancel', 'assistantApply', 'assistantUndo', 'savedViews', 'saveView', 'deleteView', 'followingStatus', 'followingPage', 'followingStart', 'followingCancel', 'followingImport', 'backgroundStatus'];
                if (!allowed.includes(method))
                    throw Error(tr("未知操作"));
                const result = await rpc(method, args, method === 'aiSearch' ? 300000 : 120000);
                if (method === 'stats')
                    libraryRoot = result.root;
                if (method === 'saveSettings' && args.proxy !== undefined)
                    await xSession.configureProxy(args.proxy);
                return result;
            }
            finally {
                if (writes)
                    ipcBusy--;
            }
        });
        win = new BrowserWindow({ width: 1480, height: 960, minWidth: 1000, minHeight: 640, backgroundColor: '#fafaf9', title: 'Luma', autoHideMenuBar: true, show: !process.argv.includes('--background'), webPreferences: { additionalArguments: ['--luma-language='+(preferences.language||'system'),'--luma-system-locale='+app.getLocale()],preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, offscreen: process.env.LUMA_UI_TEST_OFFSCREEN === '1' } });
        browserCollector = new BrowserCollector({ parent: win, rpc });
        win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
        win.webContents.on('will-navigate', e => e.preventDefault());
        win.webContents.once('did-finish-load', () => { applyPrefs(); tick(); });
        win.on('close', e => { if (preferences.closeToTray && !quitting) {
            e.preventDefault();
            win.hide();
        } });
        await win.loadFile(path.join(__dirname, '../dist/index.html'));
        tray = new Tray(trayIcon());
        tray.setToolTip(tr("Luma · 本地媒体资料库"));
        updateTray();
        tray.on('double-click', () => win.show());
        setInterval(tick, 30000).unref();
        powerMonitor.on('resume', tick);
    });
app.on('second-instance', () => { if (win) {
    if (win.isMinimized())
        win.restore();
    win.show();
    win.focus();
} });
app.on('window-all-closed', () => { if (!preferences.closeToTray)
    app.quit(); });
app.on('will-quit', () => { if (assistant)
    assistant.close().catch(() => { }); });
let exiting = false;
app.on('before-quit', e => {
    if (backend && !exiting) {
        e.preventDefault();
        exiting = true;
        quitting = true;
        rpc('shutdown', {}, 5000).catch(() => { }).finally(() => { backend.stdin.end(); const timer = setTimeout(() => { backend.kill(); app.quit(); }, 30000); backend.once('exit', () => { clearTimeout(timer); app.quit(); }); });
    }
});
