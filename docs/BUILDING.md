# 构建与验证

Build on Windows x64 with Node.js 22 and Python 3.14. Install the locked dependencies, run the checks below, preserve notices, freeze the separate core/collector programs, then package both EXEs and corresponding source archives. FFmpeg is cross-built on Ubuntu 24.04 with MinGW using `tools/build_ffmpeg.sh`; copy its `vendor/ffmpeg` and `third-party-sources` outputs to the Windows workspace. GitHub Actions automates this flow and may reuse a source-matched FFmpeg artifact/cache. Never build from a personal library. Use `LUMA_TEST_ROOT` only for disposable test profiles.

使用 Node.js 22、Python 3.14 和 Windows x64；FFmpeg 由 Ubuntu 24.04 + MinGW 交叉构建。依赖以 package-lock.json、requirements-build.lock 和 collector/engine-lock.json 为准，不从个人资料库获取任何文件。

```powershell
npm ci
node node_modules/electron/install.js
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-build.lock
.venv/Scripts/python -m unittest discover -s tests -v
node --test tests/completion.test.cjs tests/profile.test.cjs tests/assistant.test.cjs tests/workspaces-session.test.cjs tests/browser-collector.test.cjs
npm run build
```

在 Ubuntu 安装 `gcc-mingw-w64-x86-64 make` 后运行 `bash tools/build_ffmpeg.sh`。将生成的 vendor/ffmpeg 和 third-party-sources 目录复制回 Windows 构建目录。

```powershell
.venv/Scripts/python tools/prepare_notices.py
.venv/Scripts/python tools/freeze.py
$env:CSC_IDENTITY_AUTO_DISCOVERY='false'
npx electron-builder --win portable nsis --publish never
.venv/Scripts/python tools/package_release.py
```

独立采集器 EXE 不打包 gallery-dl/requests/HTTP 依赖，只保留固定版本/哈希的组件锁定表。首次使用时从官方 PyPI 取得 wheel，不调用 pip 安装到系统 Python，也不要求用户安装 Python。开发模式使用 requirements-build.lock 中已安装的依赖。

打包前必须保留原始第三方许可、NOTICE、源码及 FFmpeg 配置。`tools/freeze.py` 会从核心中排除 gallery-dl 和旧 imageio-ffmpeg，去除未使用的 OpenCV 视频插件，并检查独立采集器未混入 AI 模块。

隔离测试使用 `LUMA_TEST_ROOT` 指向临时目录，组件缓存也随之隔离。不要把它指向真实资料库，不要在其他 Luma 进程采集中执行启动/迁移测试。实际发行包还需验证启动、导入、视频封面、OCR、语义搜索和采集组件启动；真实 X 账号的访问权限/限流应单独记录，不把合成测试写成联网验收。

GEOS DLL 位于 resources/backend 的 Shapely 依赖目录，可以替换为 ABI 兼容的自编译版本。FFmpeg 是 resources/ffmpeg/ffmpeg.exe，可独立替换。优先使用安装版或解包目录进行这些修改；此项目不施加禁止反向工程以调试这些修改的条款。
