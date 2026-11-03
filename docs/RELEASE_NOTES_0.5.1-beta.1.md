# Luma 0.5.1-beta.1

English and Simplified Chinese are available in Settings. This is an unsigned Windows x64 public beta.

- Library switching now pauses background maintenance, reports progress, supports cancellation and uses a controlled desktop reload. Failures retain the old library pointer.
- Accounts gain three collection selectors with inline creation, reusable notes, editable region flags and persistent collection ordering.
- Pinned avatars no longer reload on every library revision. Avatar and nickname history are separate from the displayed avatar.
- Account removal previews shared/exclusive media, requires the account handle, preserves shared files and supports Undo. Media removal uses Trash.
- Gallery cards show original publication dates; context menus open the account inside Luma. Bulk selection actions stay visible while scrolling.
- Similarity results survive restarts. Incremental scans reuse processed items; full/scoped scans and ignored groups are available.
- Public binaries separate the GPL-3 core and GPL-2 collector integration. First collector use retrieves pinned, verified components from official PyPI hosting. Corresponding source, original notices and checksums accompany the build.

## 升级说明

新增中英文切换、三个合集下拉与新建、常用备注、可修改地区旗帜、合集拖动排序、固定头像与独立历史、上传日期、软件内账号跳转、跟随滚动的批量工具栏、相似图扫描记忆及账号清空预览/撤销。修复资料库切换后的重载锁死及恢复任务阻塞切换。

升级前请退出旧版并备份整个资料库。数据库结构为 schema 6，首次升级自动备份数据库；不建议用旧版继续打开已升级的库。新版本不会将离线库自动替换成空库。

Live X access and private/following flows still need broader live validation. Region hints do not establish nationality. Similarity is heuristic. NAS, cloud backup, automatic nudity filtering and graphical theme packs are deferred.
