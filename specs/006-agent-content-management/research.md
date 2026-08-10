# Research: 博客 Agent 内容管理

## Decision 1: 系统清单定义拓扑，数据库保存用户覆盖

**Decision**: 用版本化 system manifest 保存 Agent 稳定身份、阶段、边、锁定规则和内置默认；数据库只保存用户不可变配置版本与激活关系。

**Rationale**: 真实执行结构属于代码契约，必须随实现和测试一起发布；用户文案需要私有、可版本化和可回退。两者分离可避免数据库拓扑与 Worker 代码漂移。

**Alternatives considered**: 将所有节点和边完全落库会形成通用工作流引擎并允许绕过质量边界；继续全部硬编码则无法管理文案；每次读取源码解析 Prompt 不稳定且不可审计。

## Decision 2: 稳定 Agent 身份，不允许 MVP 任意新增生产 Agent

**Decision**: manifest 提供稳定 `agent_key`；用户可管理已注册 Agent 的内容与允许启停项，但不能创建任意生产节点。

**Rationale**: 新 Agent 不只是文案，还需要输入输出契约、门控、预算、能力和 Worker 支持。自由新增会制造界面存在但运行时不可执行的假能力。

**Alternatives considered**: 自由新增 Agent 超出博客 MVP；只显示当前五个 Agent 而无注册机制不利于后续扩展。

## Decision 3: Prompt 分层组合且安全底座锁定

**Decision**: 组合顺序为锁定系统安全段、冻结 Agent 指令、Blog Skill 规则、共享诊断/输入和本次临时要求；后层不得放宽前层。

**Rationale**: 用户需要改文案，但所有权、事实保护、输出 schema 和候选边界不能交给自由文本决定。结构化分层也便于比较和定位效果。

**Alternatives considered**: 整个 system prompt 自由编辑风险不可接受；仅提供一个附加文本框无法表达各 Agent 职责；为每篇文章复制 Prompt 会造成数据重复。

## Decision 4: 不可变版本与激活关系分离

**Decision**: 保存总是追加 AgentVersion；AgentActivation 单独指向生效版本并带乐观锁。草稿创建不自动激活。

**Rationale**: 用户可以放心试文案；并发编辑不会静默覆盖；正式任务可稳定引用版本。

**Alternatives considered**: 原地修改无法复现历史；“保存即上线”不适合 Prompt 试验；Git 文件版本不能执行每用户所有权。

## Decision 5: 正式任务冻结 eligible 版本，结果单独记录

**Decision**: 提交时冻结总控、所有可能被选择的 Agent、Skill、安全策略和能力公开清单；运行时再写 selected/skipped 与 reason code。

**Rationale**: Agent 是否选择依赖文章诊断，通常发生在 Worker；但 Worker 不能读取提交后变化的当前配置。配置快照和执行结果需要明确分开。

**Alternatives considered**: Worker 启动时读取最新配置会漂移；提交时提前运行完整诊断会拉长同步接口；只保存最终选择无法解释未选分支当时用的版本和能力状态。

## Decision 6: 自动布局真实拓扑，不做拖拽式流程编辑

**Decision**: 页面按 manifest 的 stage/order/edges 自动布局，提供语义列表替代视图；MVP 不保存坐标或用户改序。

**Rationale**: 用户要求直观地按执行结构放置，而不是设计新结构。自动布局避免视觉顺序与真实运行分叉，并天然适配窄屏。

**Alternatives considered**: 自由画布增加复杂度、无障碍困难且易暗示可改运行；纯平面列表看不出条件关系；用户仅可折叠和筛选，不改变拓扑。

## Decision 7: 复用 Blog Skill，能力作为安全清单引用

**Decision**: Blog Skill 继续使用既有表/API/版本；manifest 只存引用关系。执行能力从注册表返回 allowlisted descriptor 与健康状态。

**Rationale**: 内容规范 Skill 与工具能力职责不同，但都应出现在 Agent 的实际调用位置。复制 Skill 会造成双重真相；暴露能力原始配置可能泄密。

**Alternatives considered**: 将能力也转成 BlogSkill 混淆规范和执行器；在 Agent 版本内嵌完整 Skill 造成重复；直接返回环境 JSON 可能包含 endpoint/token_file/headers。

## Decision 8: 预览是持久化、隔离的异步任务

**Decision**: 临时样例先保存为 BlogAgentPreview，再经 AsyncJob/Outbox 派发，消息只传 ID；结果不进入文章修订或候选。

**Rationale**: Prompt/模型测试可能耗时且失败，必须满足 durable-before-intelligence；复用任务中心可见状态和重试，不增加同步超时路径。

**Alternatives considered**: 同步预览会阻塞请求；把正文塞入消息违反有界消息；复制正式文章生成临时 Post 会污染博客版本和搜索。

## Decision 9: manifest 漂移显式重验

**Decision**: AgentVersion 保存 `base_manifest_version` 与 `base_default_hash`。内置默认变化时保留用户版本，状态标为需重验；恢复默认生成新用户版本。

**Rationale**: 部署更新不能静默覆盖用户文案，也不能假设旧覆盖仍与新输出契约兼容。

**Alternatives considered**: 自动合并 Prompt 难以可靠判断语义；永久冻结旧系统安全段会错过必要修复；直接删除旧覆盖破坏用户数据。

## Decision 10: 多层防密钥泄露

**Decision**: 保存前检测常见密钥/凭据模式；API 响应使用 allowlist；能力清单剥离敏感字段；日志与 Activity 仅记录字段集合、长度、哈希和业务 ID。

**Rationale**: Prompt 管理面会鼓励粘贴文本，单靠日志清洗或用户注意不足以防止密钥进入版本历史。

**Alternatives considered**: 仅提示用户不粘贴密钥不可验证；保存后再脱敏已污染历史；加密保存密钥会错误地把本功能变成 secret manager。
