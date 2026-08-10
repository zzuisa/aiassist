# Phase 0 Research: 博客内容管理扩展

**Feature**: `005-blog-content-management`  
**Date**: 2026-07-28

本研究只解决实现计划中的架构选择与现有系统集成方式。产品范围仍以 [spec.md](spec.md) 为准。

## Decision 1: 增量扩展既有 `posts` 模块

**Decision**: 保留现有 `Post`、`PostRevision`、私有 CRUD、AI 修订和公开发布接口，在同一模块内增加来源采集、内部整理状态、结构化字段、Skill、AI 运行绑定、候选审核、分类/标签/关键词治理、时间轴与模块搜索。现有 `Post.status` 继续表达 `draft/private/published` 的发布可见性；新增 `content_status` 表达待解析、待整理、AI 处理中、已完成、归档等内部整理生命周期。

**Rationale**: 代码已经具备最小博客闭环和兼容中的公开接口。本次是总站内模块扩展，不应建立第二套 Article 模型，也不应把内部“已完成”误映射为公开发布。

**Alternatives considered**:

- 新建独立 `articles` 模块：会重复文章、修订、标签、搜索和公开兼容逻辑，拒绝。
- 直接重定义 `Post.status`：会破坏既有公开读取、RSS 和测试语义，拒绝。
- 删除公开能力：超出本增量范围并造成回归，拒绝。

## Decision 2: Markdown 作为正文唯一持久化格式

**Decision**: `Post.markdown` 继续作为当前正文的规范格式。Markdown 模式直接编辑源文本；富文本模式使用 Milkdown 的 Vue 集成，将受支持结构读写为 Markdown。MVP 明确支持 CommonMark 加表格、任务列表、代码围栏和受控扩展；Mermaid、数学公式、提示/折叠块使用稳定的围栏或指令语法保存。任何不能无损往返的内容在切换前提示并先保存版本。

**Rationale**: Milkdown 官方将自身定义为 WYSIWYG Markdown 编辑器，提供 Vue 3 集成、Markdown 读取和更新监听，适合延续现有 Markdown 数据并实现富文本体验。CommonMark 给出稳定基础语法；扩展块需要项目自有、可测试的规范，不能假设所有编辑器插件天然无损。参考：[Milkdown Vue integration](https://milkdown.dev/docs/recipes/vue)、[Milkdown documentation](https://milkdown.dev/docs)、[CommonMark 0.31.2](https://spec.commonmark.org/0.31.2/)。

**Alternatives considered**:

- HTML 作为规范格式：会让 Markdown 模式成为有损导出，并增加清洗与差异复杂度，拒绝。
- 同时持久化 HTML 与 Markdown：会产生双写一致性问题，拒绝。
- 自研 contenteditable 编辑器：功能与可访问性风险过高，拒绝。
- MVP 一次支持所有 Markdown 方言：无法证明无损往返，改为受支持能力矩阵。

## Decision 3: URL 来源先落库、后异步提取

**Decision**: URL 提交事务先创建 `PostSource` 和待解析 `Post`，同时写 Outbox；后台任务再以受限 HTTP 客户端获取页面，用 Trafilatura 提取 Markdown 主体和元数据。原始 HTML 在设置允许时写入私有对象存储，数据库仅保存有界原始文本、摘要、提取元数据和对象键。提取部分成功也提交可用字段。

**Rationale**: 这满足“先保存来源、提取失败仍可整理”。Trafilatura 2.1 官方文档支持主正文、标题/作者/日期等元数据和 Markdown 输出；HTTPX 支持显式连接/读取超时、流式读取、连接限制和关闭默认重定向。参考：[Trafilatura 2.1 quickstart](https://trafilatura.readthedocs.io/en/stable/quickstart.html)、[Trafilatura overview](https://trafilatura.readthedocs.io/en/stable/)、[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)、[HTTPX API](https://www.python-httpx.org/api/)。

**Alternatives considered**:

- 在创建请求中完成抓取：慢页面会阻塞保存，拒绝。
- 只保存提取结果不保留来源：失败不可恢复且溯源不足，拒绝。
- 建设通用爬虫平台或无头浏览器集群：复杂度明显高于个人采集收益，拒绝；登录页面降级为仅保存来源。

## Decision 4: URL 抓取执行严格 SSRF 边界

**Decision**: 仅允许 `http`/`https`；拒绝 URL 凭据、非标准危险方案和本地文件；每次 DNS 解析检查全部 IPv4/IPv6，禁止 loopback、private、link-local、multicast、reserved 和云元数据网段；默认不自动跟随重定向，每次重定向重新验证；限制端口、重定向次数、响应类型、压缩后读取字节数和总耗时；不发送用户 Cookie/认证头。

**Rationale**: 用户可控 URL 会让服务器访问任意目标。OWASP 建议限制协议、验证所有解析地址并关闭自动重定向以防校验绕过和 DNS pinning。参考：[OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)。

**Alternatives considered**:

- 只用字符串阻止 `localhost`：可被替代 IP 表示、IPv6、DNS 和重定向绕过，拒绝。
- 任意跟随重定向：可跳转到内网，拒绝。
- 全域名允许列表：对个人网页收藏过度限制；选择网络地址安全策略。

## Decision 5: 核心列关系化，动态结构字段使用版本化 JSONB

**Decision**: 标题、摘要、状态、时间、大类、内容类型、分类等高频筛选字段使用明确列和关系；类型特有字段保存在 `Post.structured_data_json`，其定义冻结在 `PostContentType.field_schema_json` 的版本快照中。每个 `PostRevision.snapshot_json` 保存该版本全部可恢复字段，而不只保存正文。

**Rationale**: 技术复盘、旅行、日记和项目字段变化频繁，逐类型建表会造成大量稀疏迁移；把所有字段都塞进 JSON 又会削弱筛选、约束和所有权关系。PostgreSQL 18 支持对 JSONB 字符串生成全文向量和使用 JSONB 操作符，适合有界动态字段，但核心关系仍应显式建模。参考：[PostgreSQL 18 text search functions](https://www.postgresql.org/docs/18/functions-textsearch.html)、[PostgreSQL 18 JSON functions](https://www.postgresql.org/docs/18/functions-json.html)。

**Alternatives considered**:

- 每个内容类型独立表：类型增加时迁移成本高，拒绝。
- 全部字段一个 JSON 文档：组合筛选和完整性校验变弱，拒绝。
- 版本只存 Markdown：无法恢复元数据和字段级 AI 应用，拒绝。

## Decision 6: AI 候选由修订快照与候选审核记录组成

**Decision**: 扩展 `PostRevision` 为不可变完整快照；`PostAICandidate` 指向 AI 修订、基线修订和 `PostAIRun`，记录 `pending/merge_required/applied/rejected/copied`、校验报告和字段决策。应用候选时必须锁定文章、再次比较基线与当前修订，并从当前快照加上选中字段生成一个新的用户确认修订。

**Rationale**: 现有正文级 AI 修订已有“候选不覆盖”和基线冲突检查，但不能表达元数据、部分字段应用和三方比较。将不可变内容快照与可变审核状态分开，可以保留完整历史并避免修改候选本身。

**Alternatives considered**:

- 直接把候选 JSON 放入 AsyncJob.result：任务保留期与文章历史耦合，难以恢复，拒绝。
- 应用时把候选修订设为 current：无法表达部分字段合并，拒绝。
- 自动三方文本合并：对个人正文风险高，MVP 只提供三方差异和字段选择。

## Decision 7: 复用总站 AsyncJob，并增加博客运行绑定

**Decision**: 通用生命周期继续使用 `AsyncJob` 的 `pending/queued/processing/waiting_user/completed/failed/cancelled`；规格中的业务阶段放入 `current_step`，`partial/timeout/retrying` 作为可序列化的派生显示状态。`PostAIRun` 一对一关联 Job，冻结文章修订、优化类型、内容大类/类型、Skill 版本、模型键、字段策略快照和请求哈希。业务变更与 Outbox 同事务，Worker 通过幂等键防止重复候选。

**Rationale**: 总站已有持久任务、SSE 回放、取消/重试和通知能力。扩展通用状态枚举会让所有模块承担博客细节；通过阶段和派生状态即可满足用户反馈，同时保留统一任务中心。

**Alternatives considered**:

- 新建博客任务中心和状态表：重复总站能力，拒绝。
- 仅使用执行器状态：不持久、不可回放，违反宪法。
- 在消息中携带全文和 Skill：载荷无界且可能泄露内容，拒绝；消息只传标识。

## Decision 8: Skill 采用“可变身份 + 不可变版本 + 唯一默认绑定”

**Decision**: `BlogSkill` 保存名称、启用状态和当前版本；`BlogSkillVersion` 保存完整规范、字段策略、模型建议、长度规则和输出 schema 版本；`BlogSkillDefault` 对 `global/category/content_type` 各作用域强制唯一有效绑定。恢复历史版本通过复制为新版本实现。

**Rationale**: 既保证用户可编辑，也保证已提交任务可复现。独立默认绑定表能直接实现手动 → 类型 → 大类 → 全局的优先级，并避免一个 Skill 上多个布尔默认标记产生冲突。

**Alternatives considered**:

- 原地修改 Skill：历史任务逻辑漂移，拒绝。
- 每个 Post 复制整份 Skill：数据重复且难以管理；任务只存策略快照和版本引用。
- 把 Skill 作为总站模型配置：超出博客边界，拒绝。

## Decision 9: AI 使用版本化结构输出与确定性保护校验

**Decision**: 新增 `blog-optimization.v1` 严格 JSON Schema/Pydantic 模型，字段包括候选正文、通用/结构化字段、建议、来源声明和风险。Worker 在模型前计算受保护 token 清单（代码围栏、行内代码、命令、URL、数字、日期和引用），模型后比较；任何改变都加入阻断性校验，除非该字段策略明确要求人工确认。模型输出不得直接改变来源或系统字段。

**Rationale**: 现有 LLM gateway 已支持严格 schema、最多一次修复和稳定错误分类。确定性前后比较比仅依赖提示词更可靠，且能把风险展示给用户。

**Alternatives considered**:

- 自由文本输出再解析：格式不稳定，拒绝。
- 只在 Prompt 中要求“不修改”：无法验证，拒绝。
- 自动接受模型新增事实：个人档案失真风险高，拒绝。

## Decision 10: 搜索延续“直接查正式数据 + 派生索引加速”

**Decision**: 模块内搜索直接对所属用户的 Post、组织关系和结构化字段执行完整性查询，并使用 `SearchDocument` 的 GIN 全文向量加速排序/高亮；每次当前修订变化写搜索 Outbox。全局搜索继续返回 `post` 分组并跳到博客模块。代码与 CJK 查询保留 `ILIKE/pg_trgm` 兜底。

**Rationale**: 当前搜索设计保证索引延迟时新记录仍可搜索。PostgreSQL 官方将 GIN 作为全文搜索首选索引，适合 100,000 篇文章目标。参考：[PostgreSQL 18 preferred text-search indexes](https://www.postgresql.org/docs/18/textsearch-indexes.html)、[PostgreSQL 18 text-search tables](https://www.postgresql.org/docs/18/textsearch-tables.html)。

**Alternatives considered**:

- 新增独立搜索服务：违反部署简化原则，拒绝。
- 只查派生索引：索引延迟会让已保存内容暂时消失，拒绝。
- MVP 引入向量搜索：规格明确推迟复杂语义关联，拒绝。

## Decision 11: 复用总站分类和标签身份，以博客扩展表承载治理属性

**Decision**: `Category(kind='post')` 与 `Tag` 继续作为共享身份和 Post 关系目标；增加 `PostCategoryProfile`（父级、排序、说明、启用）与 `PostTagProfile`/`PostTagAlias`（颜色、说明、别名、启用）承载博客治理，不改变任务/收藏现有语义。关键词使用独立 `PostKeyword`、别名和关联表。

**Rationale**: 这样既不重复基础分类/标签，也不会把博客层级、颜色、别名强加给其他模块。关键词保持独立，符合规格的概念边界。

**Alternatives considered**:

- 新建完全独立分类/标签：重复总站实体，拒绝。
- 给基础 Tag/Category 直接增加大量博客字段：扩大站点级设计范围，拒绝。
- 用 Tag 代替 Keyword：无法表达停用词、同义词和词云统计职责，拒绝。

## Decision 12: 词云使用可重建的持久快照，不成为写入依赖

**Decision**: P3 用户故事中的词云查询创建或复用 `PostWordCloudSnapshot`，以用户、来源类型和筛选规范化哈希唯一定位最后有效结果。重新生成作为低优先级异步任务写入新结果；失败继续展示上次成功快照。文章保存只发索引事件，不同步重算词云。

**Rationale**: 词云是低频探索能力，按编辑实时维护组合统计会显著增加写入复杂度；持久快照满足“重新生成”和失败回退。

**Alternatives considered**:

- 每次页面打开全表统计：100,000 篇文章时延迟不可控，拒绝。
- 每次编辑同步更新所有维度：组合爆炸且阻塞保存，拒绝。
- 仅 Redis 缓存：失败后不能保证上次有效结果，拒绝。

## Resolved Unknowns

- 正文规范格式：Markdown。
- 富文本编辑器：Milkdown Vue 集成，限定能力矩阵。
- URL 主体提取：HTTPX 安全获取 + Trafilatura 2.1 Markdown/元数据提取。
- 内部整理状态与公开状态：独立字段，保留既有公开兼容。
- 动态结构字段：关系化核心列 + JSONB，完整修订快照。
- 任务状态：复用 AsyncJob，博客阶段和派生显示状态不扩散到全局枚举。
- 搜索：PostgreSQL 直接查询与既有派生 GIN 索引组合，不新增服务。
- 词云：P3 持久快照，异步按需重建。

规划阶段无剩余 `NEEDS CLARIFICATION`。
