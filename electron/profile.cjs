const { tr } = require('./i18n.cjs');
// Keep the desktop profile outside MSIX's per-launcher AppData overlays.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const norm = p => path.resolve(p).toLowerCase();
function discoverProfiles({ current, home }) {
    const profiles = [current], packages = path.join(home, 'AppData', 'Local', 'Packages');
    try {
        for (const entry of fs.readdirSync(packages, { withFileTypes: true }))
            if (entry.isDirectory() && /^OpenAI\.Codex_/i.test(entry.name)) {
                const p = path.join(packages, entry.name, 'LocalCache', 'Roaming', 'luma-x-library');
                if (fs.existsSync(p))
                    profiles.push(p);
            }
    }
    catch { }
    return [...new Set(profiles)];
}
function chooseProfile(reports, current) {
    const primary = reports.find(r => norm(r.profile) === norm(current));
    if (primary?.error)
        throw Error(tr("当前资料库无法核对，已停止自动恢复：") + primary.error);
    if (primary && (primary.configured || primary.photos > 0 || primary.tasks > 0)) {
        // Use the explicit physical path when the apparent AppData path is an overlay alias.
        const alias = reports.find(r => norm(r.profile) !== norm(current) && !r.error && ((primary.configIdentity && r.configIdentity === primary.configIdentity) || (!primary.configured && primary.databaseIdentity && r.databaseIdentity === primary.databaseIdentity)));
        return alias || primary;
    }
    // An explicitly selected empty/offline library still represents the user's choice.
    const candidates = reports.filter(r => !r.error && (r.configured || r.databaseExists && (r.photos > 0 || r.tasks > 0)));
    const libraries = new Set(candidates.map(r => norm(r.libraryPath)));
    if (libraries.size > 1)
        throw Error(tr("发现多个旧资料库，已停止自动选择：") + candidates.map(r => tr("{0}（{1} 项媒体、{2} 个任务）", [r.libraryPath, r.photos, r.tasks])).join('；'));
    if (candidates.length)
        return candidates[0];
    const unreadable = reports.find(r => r.error);
    if (unreadable)
        throw Error(tr("旧资料库读取失败，未创建空库：") + unreadable.error);
    return primary || { profile: current, libraryPath: path.join(current, 'library'), photos: 0, tasks: 0, configured: false };
}
const excluded = new Set(['library', 'cache', 'code cache', 'gpucache', 'dawngraphitecache', 'dawnwebgpucache', 'shadercache', 'grshadercache', 'blob_storage', 'crashpad', 'crash reports', 'lockfile', 'lock', 'singletonlock', 'singletoncookie', 'singletonsocket', 'devtoolsactiveport']);
function copyProfile(source, target) {
    let count = 0;
    function copy(dir, out) {
        if (!fs.existsSync(dir))
            return;
        fs.mkdirSync(out, { recursive: true });
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
            if (excluded.has(entry.name.toLowerCase()) || entry.isSymbolicLink())
                continue;
            const a = path.join(dir, entry.name), b = path.join(out, entry.name);
            if (entry.isDirectory())
                copy(a, b);
            else if (entry.isFile()) {
                fs.copyFileSync(a, b);
                const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
                if (hash(a) !== hash(b))
                    throw Error(tr("用户配置复制校验失败：") + entry.name);
                count++;
            }
        }
    }
    copy(source, target);
    return count;
}
function prepareProfile({ current, home, inspect, snapshot }) {
    const base = path.join(home, '.luma-desktop'), target = path.join(base, 'UserData'), marker = path.join(target, 'profile-migration.json');
    if (fs.existsSync(marker)) {
        const info = JSON.parse(fs.readFileSync(marker, 'utf8'));
        if (info.version !== 1)
            throw Error(tr("未知用户配置版本"));
        if (!fs.existsSync(path.join(target, 'library-location.json')))
            throw Error(tr("用户配置中的资料库位置缺失，未创建空库"));
        return { profile: target, migrated: false, info };
    }
    if (fs.existsSync(target) && fs.readdirSync(target).length)
        throw Error(tr("发现未完成的用户配置恢复，请保留 ") + target + tr(" 并检查，未覆盖旧文件"));
    fs.mkdirSync(base, { recursive: true });
    const lock = path.join(base, 'profile-migration.lock');
    try {
        const fd = fs.openSync(lock, 'wx');
        fs.writeSync(fd, JSON.stringify({ pid: process.pid }));
        fs.closeSync(fd);
    }
    catch (e) {
        if (e.code !== 'EEXIST')
            throw e;
        let alive = true;
        try {
            const old = JSON.parse(fs.readFileSync(lock, 'utf8'));
            process.kill(old.pid, 0);
        }
        catch {
            alive = false;
        }
        if (alive)
            throw Error(tr("另一进程正在恢复旧配置，请稍后重新打开"));
        fs.renameSync(lock, lock + '.stale-' + Date.now());
        return prepareProfile({ current, home, inspect, snapshot });
    }
    const stage = path.join(base, 'UserData.pending-' + crypto.randomUUID());
    try {
        const reports = inspect(discoverProfiles({ current, home })), selected = chooseProfile(reports, current);
        fs.mkdirSync(stage, { recursive: true });
        const copied = copyProfile(selected.profile, stage);
        let library = selected.libraryPath;
        if (!selected.configured || norm(library) === norm(path.join(selected.profile, 'library'))) {
            // Copy the default in-profile DB/media as a snapshot; never merge it with another DB.
            if (selected.photos > 0 || selected.tasks > 0)
                snapshot(library, path.join(stage, 'library'));
            library = path.join(target, 'library');
        }
        const createIfMissing = !selected.configured && !selected.photos && !selected.tasks;
        fs.writeFileSync(path.join(stage, 'library-location.json'), JSON.stringify({ path: library, ...(createIfMissing ? { createIfMissing: true } : {}) }));
        const info = { version: 1, sourceProfile: selected.profile, libraryPath: library, photos: selected.photos, tasks: selected.tasks, statuses: selected.statuses || {}, copiedFiles: copied, created: new Date().toISOString() };
        fs.writeFileSync(path.join(stage, 'profile-migration.json'), JSON.stringify(info, null, 2));
        for (const p of [stage, target]) {
            const relative = path.relative(path.resolve(base), path.resolve(p));
            if (!relative || relative.startsWith('..') || path.isAbsolute(relative))
                throw Error(tr("用户配置恢复目标越界，已停止"));
        }
        if (fs.existsSync(target))
            fs.rmdirSync(target);
        fs.renameSync(stage, target);
        return { profile: target, migrated: true, info };
    }
    finally {
        fs.unlinkSync(lock);
    }
}
module.exports = { discoverProfiles, chooseProfile, prepareProfile };
