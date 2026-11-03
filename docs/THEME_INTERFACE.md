# 图片 UI 主题接口（预留，不启用主题包）

0.5 只实现默认界面、自定义空间名称和标识。没有主题商店、主题编辑器、皮肤切换按钮或自动下载素材。

收藏空间登记在用户配置目录的 workspaces.json。每项含 id、path、name、logo、appearance、themeId、themeOptions。themeId 默认 default；空间与数据独立，换主题不得修改 library-location.json、登录会话或资料库内容。

workspaceInfo.themeInterface 返回版本 1 的素材槽位：windowBackground、sidebarBackground、character、navigationIcons、buttonTextures、panelFrames、emptyIllustrations、typography、motion。未来主题包由声明式清单和图片/字体资源组成，不执行脚本。配置格式变更需升级接口版本；未知主题及无效资源回退 default。

React 组件通过 data-theme-slot 标记应用背景、侧栏和标识；其余槽位随具体组件扩展。默认 CSS 只保留空的 --luma-skin-window-background 与 --luma-skin-sidebar-background 变量，不读取任意外部样式。后续实现须限制资源在主题目录内并校验媒体类型、大小和路径，禁止远程代码。

个人参数预留：背景裁切与锚点、角色位置和尺寸、透明度、模糊、动效关闭；主题装饰与照片原件/视频播放器分层，保证文字、焦点、选中态和原图预览可辨认。图案皮肤可影响材质、图标、边框和按钮外观；功能路由与数据逻辑保持独立。

本版各空间分别保留基础显示偏好与浏览参数；X 登录暂在本机共享同一 persist:luma-x 会话，界面明确说明。独立 X 身份分区属于后续扩展，未以独立资料库冒充独立登录。
