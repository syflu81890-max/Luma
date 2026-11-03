# 对应源码与构建材料

每个公开二进制版本都应在同一 GitHub Release 提供：

1. `Luma-<version>-source.zip`：该版本 Luma 界面、后台、独立采集器、协议集成、依赖清单、许可和构建脚本。
2. `Luma-<version>-third-party-sources.zip`：FFmpeg、GEOS 等随包组件的对应源码，以及其确切构建配置、依赖清单、第三方声明和许可。独立采集器的 Luma 源码包含在第一个包中；gallery-dl/requests 由最终用户首次使用时直接从官方 PyPI 获取，不嵌入发行 EXE。
3. `SHA256SUMS.txt`：上述文件及实际 EXE 的 SHA-256。

根目录 LICENSE 适用于 Luma 核心；collector/LICENSE 适用于独立采集器集成。Electron、Python、AI 组件和其他依赖保持各自原许可，全文位于发行包 resources/licenses。Electron 自身的 LICENSE 与 LICENSES.chromium.html 位于其发行目录。

FFmpeg 为独立命令行程序，由 `tools/build_ffmpeg.sh` 从固定上游提交构建，关闭 GPL、nonfree、version3 与自动依赖发现，启用 Windows 系统 Schannel。其源码、配置与脚本和二进制一同提供。主程序通过子进程读取视频封面，不链接 FFmpeg 库。

源码入口：<https://github.com/syflu81890-max/Luma>。构建过程见 `docs/BUILDING.md`；若某次发行缺少对应材料，该次二进制不能发布，不能只用一个上游主页链接代替源码包。
