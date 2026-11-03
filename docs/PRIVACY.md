# 隐私与本地数据

Luma stores originals, thumbnails, account information, capture tasks, deletion exclusions and AI indexes in the library you select. Preferences normally use `%USERPROFILE%/.luma-desktop/UserData`. X sessions are stored locally in Electron's session partition and may be shared across library spaces. Switching libraries does not switch the signed-in X identity. Necessary cookies are passed to the collector through stdin, not command-line arguments.

Capture connects to X and its media CDN using the configured proxy. First collector use retrieves pinned, hash-checked components from official PyPI hosting and caches them locally. Optional semantic models download from Hugging Face at a pinned revision; image inference and indexing stay on the PC. Luma has no built-in telemetry or cloud inference uploads.

The assistant port is off for fresh profiles; explicit saved preferences are retained. When enabled it binds only to loopback and requires a random token stored in the local connection file. Treat that token as permission to manage the library. Never publish it or forward the port to the Internet.

Deletion uses Trash first. Purging files retains capture exclusions; backups, undo records, account history, custom avatars and exported copies have separate lifetimes. Account removal with Undo is not secure erasure. Uninstalling the app normally leaves the user library intact. Redact credentials, private paths and media before reporting a problem; maintainers do not need login credentials.

Luma 将原件、缩略图、账号资料、任务、删除排除与 AI 索引保存在用户选择的本地资料库。默认用户配置位于 `%USERPROFILE%/.luma-desktop/UserData`。更换 EXE 或安装目录不表示更换资料库。

X 登录保存在本机 Electron 会话分区。采集器只在执行时经 stdin 接收所需 Cookie；不在命令行、源码包或问题报告中携带 Cookie。登录身份与资料库分开保存，同一 Windows 用户的收藏空间可共用 X 会话。

采集会连接 X 和对应媒体 CDN；代理配置交给这些网络请求。首次使用采集功能时从官方 PyPI 文件服务下载 `collector/engine-lock.json` 中锁定的 gallery-dl 及 HTTP 依赖，验证每个文件的 SHA-256 后缓存到 `%USERPROFILE%/.luma-desktop/Components`；已准备好的组件可重复使用，资料库本身不上传。准备失败会明确报错，重试保留任务和已下载媒体。

可选语义模型首次安装会连接 Hugging Face 下载指定模型；索引与搜索在本机执行，Luma 不上传图库做云端推理。软件没有内置遥测和使用统计服务。

本机助手默认绑定 `127.0.0.1:48120`，使用随机访问密钥；可在设置中关闭或重新生成密钥。密钥保存在配置目录，应视同本机管理权限，不要贴入公开 Issue。接口不提供 Cookie 或关机操作。不要通过端口映射把该服务直接暴露到互联网。

删除先进入资料库回收站。清空回收站会删除文件，但会保留下载排除记录；备份、账号历史、自定义头像和外部导出副本有独立生命周期。卸载软件通常不会自动删除用户资料库。

报告问题前去掉账号、媒体、磁盘路径、Cookie、助手密钥和其他私密内容。维护者不需要你的登录凭据。
