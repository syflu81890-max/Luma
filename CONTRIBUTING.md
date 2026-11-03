# 参与贡献

English and Chinese reports are welcome. Start with an Issue describing the practical problem, steps to reproduce and expected behavior. Use synthetic media and a temporary library or a read-only copy when investigating storage problems. Never commit sessions, account lists, private media, databases, logs or download caches.

Run the Python/Node checks and production build in `docs/BUILDING.md`. Changes to migration, deletion exclusions, incremental capture or backups need corresponding behavior checks. Use synthetic screenshots for UI work and check larger text and displays. Contributions follow the license of the modified directory. Keep the GPL-2 collector process separate from the GPL-3 library/AI core. Changes exposing the local assistant directly to the Internet or bypassing account access restrictions are outside scope.

建议先用 Issue 描述问题、复现步骤和预期行为。修复资料库问题时使用临时库或只读副本，不在真实采集中执行迁移测试。不要提交任何会话、账号清单、私人媒体、数据库、运行日志或下载缓存。

提交前运行 Python/Node 验证和生产构建，命令见 docs/BUILDING.md。改变迁移、删除排除、增量边界或备份时需要相应的行为验证。UI 修改应使用合成数据截图，并检查大字体和大屏。

贡献遵循所修改目录的许可证。采集器和 AI/图库保持独立进程，不把 gallery-dl 直接导入核心后台。暂不接收把本机助手直接开放到公网或绕过账号访问权限的改动。
