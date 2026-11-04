# Luma 0.5.1-beta.2

Hotfix for magenta/green scanlines in video covers introduced in beta.1.

- Extract video covers through portable CPU code. The Windows FFmpeg optimized path could return success while producing corrupted frames.
- Regenerate legacy video posters on first access, including MP4-backed GIFs. New posters use a separate versioned cache and atomic writes. Original videos, metadata, tasks and collection progress are retained.
- Add patterned 720×1280 H.264 checks that measure picture colors and structure, including in the frozen backend. Earlier flat MPEG-4 checks did not expose this defect.

## 中文

修复新版采集的视频封面出现紫绿条纹、花屏的问题。已下载的视频无需重下，更新后首次浏览会自动重建视频封面。视频文件、备注、合集及任务不变；不需要重置资料库。

退出旧版后再运行新版；正在采集时先等待任务结束或暂停。保持 schema 6，无新增数据库迁移。仍为未签名的 Windows x64 测试版，其他已知范围见 [beta.1](RELEASE_NOTES_0.5.1-beta.1.md)。
