const { tr } = require('./i18n.cjs');
// Session-only completion plan. All system effects are injected for safe tests.
class CompletionController {
    constructor({ backend, execute, publish = () => { }, now = () => performance.now(), countdown = 60000 }) {
        Object.assign(this, { backend, execute, publish, now, countdown });
        this.state = { phase: 'off', action: 'none', remaining: 0, total: 0, complete: 0, message: '' };
        this.chain = Promise.resolve();
        this.deadline = 0;
    }
    serial(fn) { const next = this.chain.then(fn); this.chain = next.catch(() => { }); return next; }
    current() { return { ...this.state }; }
    emit(values) { Object.assign(this.state, values); this.publish(this.current()); return this.current(); }
    arm(action, waitAnalysis = false) {
        return this.serial(async () => {
            this.cancelRequested = false;
            if (!['shutdown', 'sleep'].includes(action))
                throw Error(tr("无效完成后动作"));
            await this.backend({ action: 'cancel' });
            const s = await this.backend({ action: 'arm', waitAnalysis });
            this.deadline = 0;
            this.generation = s.generation;
            return this.emit({ phase: 'waiting', action, waitAnalysis, remaining: 0, total: s.total, complete: s.complete || 0, message: tr("本轮完成后") + (action === 'shutdown' ? tr("关机") : tr("睡眠")) + tr("；未来定时暂缓，手动新增会加入本轮") });
        });
    }
    cancel(message = tr("已取消本次完成后动作")) { this.cancelRequested = true; return this.serial(() => this._cancel(message)); }
    async _cancel(message, phase = 'off') {
        this.deadline = 0;
        await this.backend({ action: 'cancel' });
        return this.emit({ phase, action: 'none', remaining: 0, message });
    }
    tick() {
        if (this.tickPending)
            return Promise.resolve(this.current());
        this.tickPending = true;
        return this.serial(async () => {
            if (!['waiting', 'countdown', 'preparing'].includes(this.state.phase))
                return this.current();
            try {
                const s = await this.backend({ action: 'status' });
                if (this.cancelRequested)
                    return this.current();
                this.state.total = s.total || 0;
                this.state.complete = s.complete || 0;
                if (!s.armed)
                    return this.emit({ phase: 'off', action: 'none', remaining: 0, message: tr("完成后动作已取消") });
                if (s.reason)
                    return this._cancel(s.reason, 'blocked');
                if (!s.ready || s.generation !== this.generation) {
                    this.deadline = 0;
                    this.generation = s.generation;
                    return this.emit({ phase: 'waiting', remaining: 0, message: s.busy ? tr("等待采集、分析或文件写入结束") : tr("等待本轮采集全部成功完成") });
                }
                if (!this.deadline)
                    this.deadline = this.now() + this.countdown;
                const remaining = Math.max(0, Math.ceil((this.deadline - this.now()) / 1000));
                if (remaining)
                    return this.emit({ phase: 'countdown', remaining, message: remaining + tr(" 秒后") + (this.state.action === 'shutdown' ? tr("关机") : tr("睡眠")) + tr("，可以取消") });
                this.emit({ phase: 'preparing', remaining: 0, message: tr("正在保存资料库，准备") + (this.state.action === 'shutdown' ? tr("关机") : tr("睡眠")) });
                const ready = await this.backend({ action: 'prepare' });
                if (!ready.ready || this.cancelRequested)
                    return this.current();
                await this.execute(this.state.action);
                return this.emit({ phase: 'executed', remaining: 0, message: tr("完成后动作已交给系统") });
            }
            catch (e) {
                try {
                    await this.backend({ action: 'cancel' });
                }
                catch { }
                this.deadline = 0;
                return this.emit({ phase: 'error', action: 'none', remaining: 0, message: tr("完成后动作未执行：") + e.message });
            }
        }).finally(() => { this.tickPending = false; });
    }
}
module.exports = { CompletionController };
