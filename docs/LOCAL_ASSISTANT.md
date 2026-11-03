# Luma 0.4.0 本机助手接口

首次运行默认关闭本机助手。设置 → 本机助手连接可显式启用 `http://127.0.0.1:48120`、关闭、改端口（0 为自动分配）、更换密钥、复制连接文件路径。已有明确开启的设置继续保留。端口被其他软件占用时明确报错，不连接其他服务。

这是供当前电脑上的 Codex/脚本管理图库的接口。只监听 IPv4 回环地址，每次启动产生 256 位随机密钥。所有端点需要 `Authorization: Bearer <token>`。拒绝浏览器 Origin / Fetch Metadata 请求，不开放 CORS，不监听局域网。NAS 和远程访问未开放。

## 找到运行中的软件

读取 `%USERPROFILE%/.luma-desktop/UserData/assistant-connection.json`。隔离测试使用各自 profile 下的连接文件。文件有 `url`、`token`、`pid`、`running` 等字段。密钥仅保存在本机，不把它打印到聊天、日志、源码或 GitHub。退出、禁用后连接失效；重启和更换密钥后需重新读取文件。

随发行包附带 `resources/assistant/luma_assistant.py` 和本说明。源码中客户端位于 `tools/luma_assistant.py`。客户端使用 Python 标准库，无第三方依赖；直接访问 HTTP 则不要求本机额外安装 Python。Codex 在当前源码目录可以执行：

```powershell
.venv/Scripts/python -X utf8 tools/luma_assistant.py status
.venv/Scripts/python -X utf8 tools/luma_assistant.py capabilities
.venv/Scripts/python -X utf8 tools/luma_assistant.py stats
.venv/Scripts/python -X utf8 tools/luma_assistant.py list --file request.json
```

`request.json` 为普通 JSON 参数对象，建议中文、多行提示词和 Windows 路径用 UTF-8 文件传递，避免 Shell 转义。`--connection` 可指定其他连接文件。

HTTP 接口：`GET /v1/status`、`GET /v1/capabilities`、`POST /v1/rpc`。POST 的 Content-Type 为 application/json，请求体不超过 1 MiB：

```json
{"method":"list","args":{"kind":"image","limit":60,"page":1,"q":"鞋子"}}
```

返回 `{"result":...}`；出错返回非 2xx 和 `{"error":"..."}`。客户端显示结果时不显示密钥。请求超时后先查状态，不盲目重复有副作用的操作。

## 去重与整理

`stats`、`list`、`detail`、`files`、`accounts`、`account`、`taskPage`、`storageStatus`、`libraryLocation`、`aiSearch` 可读。`files` 返回所选 ID 对应的本地原件路径，可用图片查看工具检查。`list` 每页最多 240 项，账号卡片默认 64，支持 32/64/96/128；任务列表默认 100，支持 50/100/200。`aiSearch` 需要已安装的本地模型与索引。

`assistantDuplicates` 参数：`filters`（与图库筛选相同）、`threshold`（0–12，默认 4）、`offset`、`limit`（最多 50 组）。仅查照片感知相似，返回每组详情及建议保留 ID，不更改图库。相似组可包含传递相似的图片，并不保证组内每两张都相似，必须看图后决定。完全相同文件入库时已去重；多个账号、分类文件夹里的硬链接共用同一原件，不应把这些目录项当重复媒体删除。

整理分两步，可由助手在用户已授权的整理范围内连续执行，无需每批重复人工确认：

1. `assistantPlan` 指定 `ids` 或明确的 `filters`，以及 `action`、`value`。支持 `tags`（mode 为 add/remove/replace）、`favorite`、`reviewed`、`note`、`trash`、`restore`。不传选择范围会报错；全库需明确 `filters:{}`。每批 1–5000 项。
2. 查看返回清单/`assistantPlanInfo {id}` 后，用 `assistantApply {id}` 执行。计划保存操作前状态；内容变化会拒绝执行，需重新生成。重复执行同一已完成计划不重复处理。

删除只进回收站并写删除排除记录。恢复会解除排除。没有对外开放彻底删除。最近一次计划可以用 `assistantUndo {id}` 撤销；若其后已有别的编辑会拒绝，避免误撤销别人操作。也可在软件内撤销最近编辑。

其他管理方法：`saveAccount` 修改账号评分/分类/别名/备注，`album` 创建相册或增删所选关联，`addTask`（limit 默认 0 不限）、`taskAction`（pause/resume/cancel）、`organizeStorage` 整理已有磁盘目录。账号分类调整可能同时更新物理树状目录。登录会话由 Electron 内部注入任务，不向接口返回 Cookie。不开放 Shell、系统电源动作、切换资料库、登录凭据或任意后台方法。

## 指定文件夹和 AI 改图

`assistantFolder {path,recursive:true,offset:0,limit:100}` 只读列出文件夹里的静态照片，返回路径、尺寸、SHA-256、是否已在库中。每页最多 200 项；按 nextOffset 继续，null 为结束。外部文件夹不会自动导入、修改或删除；GIF/视频不进入这一改图流程。

1. 调用 `assistantEditPrepare`：`ids:[图库ID]` 或 `paths:[外部照片路径]`，`references:[人物参考照片路径]`，`prompt:"修改要求"`。每作业最多 100 张，人物参考最多 10 张。输入和参考保存为独立副本，不用硬链接，返回 input、reference 绝对路径和作业 ID。
2. 助手先用图片查看工具检查输入和参考，再使用当前对话可用的图片编辑工具。每张输入分别执行，遵守工具要求及用户的人物、隐私和编辑范围。涉及 Luu 时沿当前 Luu 技能和最新规则执行。仅开端口不会把图片交给云端；实际调用外部图片工具时才会发送所选图片。
3. 图片工具返回本地结果后，调用 `assistantEditCommit {id:作业ID,index:输入序号,path:结果文件}`。将结果校验后导入图库，作为关联原件的独立版本，继承标签、相册、账号关联和推文来源，增加 AI修改 标签。输入原图和外部文件夹保留。
4. `assistantJob {id}` 查看/继续作业；`assistantJobs` 返回最近 100 个作业。每张结果可独立回库，中断后可从未完成项继续。已存在于图库的结果不会被强行重新挂接到其他原件。输入副本被更改则拒绝交接。资料库备份/迁移包含作业，内部输入/参考路径在新库中重定位。

作业位于 `library/edits/assistant/jobs/`；整理计划位于 `library/edits/assistant/plans/`；操作记录在 `library/edits/assistant/activity.jsonl`，不写连接密钥或 Cookie。

Luma 不内置图片生成模型，也不自动操作 ChatGPT 网页或复用网页登录调用 API。你在当前对话里让 Codex 修改时，可以使用该对话提供的图片工具；脱离对话自动云端批量生成需要另外配置生成服务。此接口本轮提供本机管理和文件交接。


## 0.4 管理扩展

`dashboard` 返回总览数字与七天入库；`collections` / `collectionAction` 管理账号合集；`accountHistory` 查询曾用名和头像记录；`accountHealthCheck {ids?:[...]}` 启动账号检测（默认检测整个封禁池），`accountHealthStatus` 返回进度。检测向 X 查询身份状态，使用本机已登录会话，不上传图库照片。只有明确封禁结果进入封禁池，网络/登录失败保留原状态。`collectAll` 更新普通账号并跳过已排队的账号，封禁账号不会加入队列。

`similarScan` 启动后台像素验证；`similarStatus` / `similarPage {page}` 读取进度和图片组；`similarCancel` 停止检查；`similarPlan {groups?:[组ID],protectFavorites:true}` 创建保留最高像素的整理计划，再经 `assistantApply {id}` 执行，`assistantUndo {id}` 撤销。扫描仅提取候选，原件发生变化时拒绝处理。收藏默认保留，parent 非空的 AI 修改版本不参与。全部接口仍只在本机授权连接开放，不包含系统电源或登录凭据读取。
