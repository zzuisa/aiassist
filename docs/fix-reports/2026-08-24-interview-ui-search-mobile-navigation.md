# 修复复盘：Interview 风格重构后的搜索与移动导航交互（2026-08-24）

## 现象

- 用户在 Header 全局搜索框提交关键词后会进入 `/search?q=...`，但搜索页输入框仍为空，也不会自动执行搜索。
- 在移动端页面已经向下滚动时打开浮动导航，页面根容器被压缩为一个视口高度；关闭导航后滚动位置回到顶部。
- 移动导航关闭后虽然不可见，但其中的链接仍可能进入键盘焦点顺序；打开后按 Tab 也可以离开菜单，关闭后焦点没有回到触发按钮。
- Header 中的 Interview 应用切换链接使用 `/interview/` 相对地址，在 AI Assist 域名下会回到 AI Assist，而不是实际 Interview 产品。
- 新增的导航、输入框和 Agent 对话样式仍散落少量颜色、阴影及移动端避让尺寸硬编码；响应式文件声明的 CSS breakpoint 变量无法用于 `@media` 条件，容易形成错误的“统一断点”认知。
- 移动导航底部“保持专注”看起来像可执行按钮，实际只会关闭菜单，没有对应业务动作。

## 影响

- 全局搜索的主要入口不可用，用户必须在搜索页重复输入关键词。
- 移动端打开导航会打断阅读或对话上下文，长页面尤其明显。
- 键盘和辅助技术用户可能聚焦到不可见内容，导航弹层不符合预期的对话框焦点行为。
- Interview 与 AI Assist 的跨产品导航失效，破坏同一设计体系下的模块切换体验。
- 视觉值继续分散会增加后续 Interview 设计体系同步成本。

## 根因

1. `AppShell` 正确把 Header 关键词写入路由查询参数，但 `SearchPage` 只监听本地 `query`，没有读取或监听 `route.query.q`。
2. 移动导航用 `.navigation-open { height: 100vh; overflow: hidden; }` 锁滚动，改变了文档根容器高度，浏览器因此夹取并丢失原滚动位置。
3. 关闭态导航仅使用 `opacity: 0` 和 `pointer-events: none`；这两项不会从可访问性树和键盘焦点顺序中移除元素，也没有实现焦点圈定与恢复。
4. Interview 链接沿用了同域相对路径假设，但生产环境实际产品地址是独立站点 `https://roguelife.de/interview/`。
5. CSS 自定义属性不能作为媒体查询条件参与计算，原 breakpoint 变量只是普通声明；部分视觉常量在组件迁移时没有及时归入 Interview token 层。
6. 进度提示被错误建模为按钮，却没有业务行为。

## 修改

- 搜索页监听 `route.query.q`，兼容字符串和数组查询参数；Header 搜索跳转后自动回填并执行现有防抖搜索，同时在组件卸载时清理定时器。
- 新增共享 `useMediaQuery` composable 和唯一的 shell 紧凑布局查询常量，供 Vue 交互状态判断复用。
- 移动导航改为给 `body` 增加滚动锁，不再修改页面根容器高度；关闭或卸载 shell 时保证清除锁定类。
- 关闭态移动导航增加 `inert` 与 `aria-hidden`；打开态使用 modal dialog 语义，自动聚焦当前导航项，在首尾焦点间圈定 Tab，并在 Escape、遮罩或按钮关闭后把焦点恢复到触发按钮。
- 将 Interview 链接改为已确认的绝对产品地址。
- 将导航、焦点、运行状态、对话输入区的颜色、渐变、阴影和移动端浮动导航避让尺寸集中到 `tokens.css`；移除无法生效的 breakpoint CSS 变量，并明确记录 Interview 的 1050px/700px 规范断点。
- 将无行为的“保持专注”按钮改为静态状态说明。
- 新增搜索路由联动以及移动导航滚动锁、`inert`、焦点圈定和焦点恢复的组件回归测试。

## 验证

- 在 Node 24 容器中运行 ESLint，零错误、零警告。
- 前端完整 Vitest：42 个测试文件、188 项测试全部通过。
- `vue-tsc` 类型检查通过。
- Vite 生产构建成功，PWA Service Worker 与预缓存清单正常生成。
- 定向回归确认：`q` 参数会回填搜索框并调用搜索 API；移动菜单关闭态为 `inert`，打开时锁定 `body`，Tab 在菜单内循环，关闭后焦点回到菜单按钮。
- 修复提交 `e8a0485` 已通过快速部署进入生产；backend、frontend、worker-fast、worker-heavy 与 nginx 网关健康检查全部通过，数据库迁移保持在当前 head。
- 生产 Chromium 在 390px 视口验证：打开和关闭导航前后 `scrollY` 均为 500、文档高度均为 2895；搜索页正确回填“情感文章”，关闭导航后焦点回到触发按钮，Interview 链接为 `https://roguelife.de/interview/`。
- 本复盘已通过 AI Assist API 归档为内部草稿，业务对象 ID 为 `0b19f0ed-7386-4d1e-ac45-f1377ada018e`，分类为“AI Assist 修复复盘”，未调用公开发布接口。

## 日志检索方式

本次问题主要发生在浏览器前端状态，优先使用浏览器开发者工具确认：

```text
Network: /api/v1/search?q=<关键词>
Elements: body.mobile-nav-open、#primary-navigation[inert]、aria-hidden、aria-modal
Console: TypeError、Unhandled Promise、Vue warn
```

生产网关与前端容器可使用以下安全检索，不记录查询正文、Cookie 或认证头：

```bash
./deploy/scripts/deploy.sh logs nginx | rg '/api/v1/search|/search| 4[0-9][0-9] | 5[0-9][0-9] '
./deploy/scripts/deploy.sh logs frontend | rg 'error|warn|exception'
```

需要复现滚动问题时，仅记录 `window.scrollY`、`document.documentElement.scrollHeight` 和视口尺寸，不采集页面内容。

## 遗留风险

- `body { overflow: hidden; }` 在现代 Chromium、Firefox 和 Safari 中可保留滚动位置；极旧版 iOS WebKit 的滚动锁行为仍可能不同，需要保留真实设备抽查。
- CSS 媒体查询仍必须使用 1050px/700px 字面量，因为原生 CSS 自定义属性无法用于媒体条件；Vue 交互侧已经通过共享常量避免重复。
- 生产构建仍报告既有的大 chunk 警告；与本次交互故障无关，后续应单独评估编辑器、图表和 Markdown 依赖的按需拆包。
- 部分既有组件测试仍输出未 stub `RouterLink` 的 Vue 警告，但测试全部通过；后续可在测试基础设施层统一提供 Router stub。
