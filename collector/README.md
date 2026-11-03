# Luma 独立采集器

本目录中的 Luma 集成代码采用 GPL-2.0-only。公开 EXE 不嵌入 gallery-dl 或 requests：首次使用时从官方 PyPI 下载 `engine-lock.json` 中固定版本的 wheel，验证 SHA-256 后放入独立缓存，直接保留 wheel 内原始许可/NOTICE。gallery-dl 及其依赖各自保留上游版权和许可证；不将它们改授为 Luma 的许可。此目录不包含 AI、图库或数据库模块。

可以独立运行：`python collector/app.py --version`。操作标志为 `--download`、`--following`、`--probe-account`；标准输入传入一个 JSON 对象，标准输出为 JSON 行。认证仅通过本次调用的 stdin 传递，不作为命令行参数写入进程列表。

下载请求支持 url、stage、cookies、proxy、ffmpeg、mode、known、excluded、watermark、limit、options 和 selected；详细字段使用见 `backend/service.py`。账号探测与关注读取使用 handle/owner、cookies、proxy。进程可在终止后由调用方根据已保存游标继续。

图库主程序通过 `backend/collector_client.py` 启动独立 EXE，读取普通媒体元数据事件。采集器不访问 library.db，不写账号评分、相册和本地 AI 索引。输入的 stage 是临时下载目录。
