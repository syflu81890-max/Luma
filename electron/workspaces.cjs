const { tr } = require('./i18n.cjs');
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const normalize = p => { const absolute = path.resolve(p); try { return fs.realpathSync.native(absolute).toLowerCase(); } catch { return absolute.toLowerCase(); } };
const sameWorkspacePath = (a, b) => normalize(a) === normalize(b);
const idFor = p => crypto.createHash('sha256').update(normalize(p)).digest('hex').slice(0, 20);
class Workspaces {
    constructor(profile) { this.profile = profile; this.file = path.join(profile, 'workspaces.json'); this.items = []; if (fs.existsSync(this.file)) {
        const data = JSON.parse(fs.readFileSync(this.file, 'utf8'));
        if (data.version !== 1 || !Array.isArray(data.items))
            throw Error(tr("收藏空间配置无法读取，原资料库指针保持不变"));
        let merged = false;
        for (const row of data.items) {
            if (!row || typeof row.id !== 'string' || typeof row.path !== 'string')
                throw Error(tr("收藏空间配置无法读取，原资料库指针保持不变"));
            const existing = this.items.find(item => sameWorkspacePath(item.path, row.path));
            if (!existing) { this.items.push(row); continue; }
            // Preserve the original stable ID and manual appearance. Retain old
            // IDs so already-open selectors can still resolve a merged alias.
            existing.aliases = [...new Set([...(Array.isArray(existing.aliases) ? existing.aliases : []), row.id, ...(Array.isArray(row.aliases) ? row.aliases : [])])];
            existing.appearance = { ...(row.appearance || {}), ...(existing.appearance || {}) };
            if (!existing.logo && row.logo) existing.logo = row.logo;
            merged = true;
        }
        if (merged) {
            const backup = path.join(profile, 'workspaces.before-alias-dedupe.json');
            if (!fs.existsSync(backup)) fs.copyFileSync(this.file, backup);
            this.write();
        }
    } }
    write() { fs.mkdirSync(this.profile, { recursive: true }); const temp = this.file + '.pending'; fs.writeFileSync(temp, JSON.stringify({ version: 1, items: this.items }, null, 2)); fs.renameSync(temp, this.file); }
    track(root) { let row = this.items.find(w => normalize(w.path) === normalize(root)); if (!row) {
        row = { id: idFor(root), path: path.resolve(root), name: this.items.length ? path.basename(root) : tr("我的收藏"), themeId: 'default', themeOptions: {}, appearance: {} };
        this.items.push(row);
        this.write();
    } return row; }
    info(root) { const current = this.track(root); return { current: this.present(current), items: this.items.map(w => this.present(w)), themeInterface: { version: 1, active: 'default', slots: ['windowBackground', 'sidebarBackground', 'character', 'navigationIcons', 'buttonTextures', 'panelFrames', 'emptyIllustrations', 'typography', 'motion'] } }; }
    present(row) { let logo = ''; if (row.logo) {
        try {
            const file = path.resolve(row.logo), allowed = path.resolve(this.profile, 'workspace-assets');
            if (file.startsWith(allowed + path.sep) && fs.statSync(file).size < 2 * 1024 * 1024)
                logo = 'data:image/png;base64,' + fs.readFileSync(file).toString('base64');
        }
        catch { }
    } return { ...row, logo, available: fs.existsSync(path.join(row.path, 'library.db')) }; }
    save(root, values) { const row = this.track(root); if (values.name !== undefined) {
        const name = String(values.name).trim();
        if (!name || name.length > 40)
            throw Error(tr("空间名称为 1–40 字"));
        row.name = name;
    } if (values.logo !== undefined)
        row.logo = values.logo; this.write(); return this.info(root); }
    get(id) { const row = this.items.find(w => w.id === id || Array.isArray(w.aliases) && w.aliases.includes(id)); if (!row)
        throw Error(tr("收藏空间不存在")); return row; }
}
module.exports = { Workspaces, idFor, sameWorkspacePath };
