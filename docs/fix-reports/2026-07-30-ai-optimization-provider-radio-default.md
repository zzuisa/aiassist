# 修复复盘：文章 AI 优化服务选择与 Radio 默认接入（2026-07-30）

## 现象与目标

文章编辑页已有“AI 优化”入口和一个可填写的 `model_key`，但该字段只被记录在运行数据中，实际调用始终固定走 AI Assist 的 LLM gateway。用户无法在点击优化后选择具体 AI，也无法在设置中配置默认服务。

本次目标是把 Radio 的 Gemini 轻量文章优化作为正式选项并设为默认，同时保留 AI Assist 的完整结构化优化能力。每次任务必须冻结所选服务，后续修改默认值不能影响已经提交的任务。

## 根因

1. `PostAIRun` 只记录模型名，没有记录真正的 provider。
2. Worker 不读取 `model_key` 进行路由，所有优化固定调用 `get_llm_gateway()`。
3. Radio 原接口只能按其内部 transcript ID 优化历史转写，不能接收 AI Assist 的任意 Markdown 正文。
4. `BlogSettings.ai_apply_json` 已存在，但没有默认优化 provider 字段，设置页也没有对应控件。

## 修改

### Provider 固定绑定

- 新增稳定 provider：`radio`、`aiassist`。
- `PostAIRun.provider_key` 在提交时冻结，并参与输入哈希和重复任务判定。
- migration `0014_ai_optimization_provider` 将历史运行回填为 `aiassist`，新任务使用用户设置。
- 后端未显式传 provider 时读取用户默认值；有效默认值为 `radio`。

### Radio 正文优化 API

- Radio 新增受认证接口 `POST /api/text/optimize`。
- 接收 Markdown 正文和可选附加指令，复用 Radio 当前 Gemini 配置。
- Prompt 要求保留 Markdown、代码块、命令、链接、数字、日期、引用和事实，只做轻量语言优化。
- 外部请求设置 5 秒连接超时、150 秒读取超时，不记录正文、密码、Cookie 或模型响应。

### AI Assist Worker

- `provider_key=radio` 时通过 Radio HTTP 客户端优化正文。
- Radio 结果被转换为 `blog-optimization.v1` 的正文候选，继续执行保护内容比较、字段策略和候选审核。
- 当前文章不会被自动覆盖；用户仍需在候选对比页审核后应用。
- Radio 连接、超时、5xx 或空响应映射为稳定错误码和明确提示。
- `provider_key=aiassist` 保留原完整结构化优化，可处理标题、摘要、元数据、分类建议、Skill 和模型覆盖。

### 前端与设置

- AI 优化弹窗增加“使用哪个 AI”选择器。
- 默认显示 `Radio（Gemini 轻量正文优化）`。
- Radio 模式固定为“语言润色 + 仅正文”，避免暗示它会生成元数据。
- 切换到 AI Assist 后显示完整优化类型、范围、Skill、模型和附加指令。
- 设置页增加“默认优化服务”，可在 Radio 与 AI Assist 之间切换。
- 设置 API 返回 provider 的配置和健康状态；当前默认已显式保存为 Radio。

## 现网验证

### Radio 接口

使用短测试文本调用真实 Radio Gemini 接口：

~~~text
authentication: success
HTTP result: success
optimized result: non-empty
result chars: 14
~~~

测试输出和日志只记录长度，没有记录正文或模型响应。

### 完整 AI Assist 链路

对内部修复报告提交 Radio 优化：

~~~text
HTTP submit:          202
job type:             blog.optimize
provider_key:         radio
job status:           waiting_user
progress:             100
run outcome:          complete
candidate status:     pending
candidate created:    yes
post version changed: no
current body chars:   4291
candidate body chars: 4596
saved default:        radio
Radio dependency:     ready
~~~

当前文章没有被覆盖，只新增了一份待审核候选。

## 自动化验证

~~~text
后端定向测试：78 passed
前端组件测试：17 passed
Radio 接口与分页测试：2 passed
前端生产构建：passed
数据库 migration/model drift：passed
Ruff（本次核心改动）：passed
compileall：passed
git diff --check：passed
现网 gateway：ready
fast worker：healthy
heavy worker：healthy
~~~

覆盖默认 provider、设置持久化、非法 provider、任务 provider 固定绑定、输入哈希、AI Assist 原链路、Radio 成功与空响应、候选不覆盖正文、任务幂等、迁移无漂移和前端 provider 选择。

## Kibana 检索

Data view：`logs-aiassist-*`

~~~text
event: "blog_optimize_completed" and provider_key: "radio"
event: "blog_optimize_failed" and provider_key: "radio"
job_id: "076b1c07-eb8f-4556-a194-23a13a86410c"
provider_key: "radio"
error_code: "RADIO_SERVICE_UNAVAILABLE"
trace_id: "<任务详情中的 trace ID>"
~~~

成功日志包含 `run_id`、`post_id`、`job_id`、`provider_key` 和 `outcome`；失败日志增加稳定错误码和安全诊断分类，不包含正文或鉴权数据。

## 回滚

- 应用回滚：切换到上一版镜像；新增列可先保留，旧代码不会读取它。
- 设置回滚：在设置页把默认服务改回 AI Assist，不影响已经提交的运行。
- Schema 回滚：确认不再运行新代码后执行 `alembic downgrade 0013_radio_bilibili_import`；这会删除 provider 固定绑定信息。
- Radio 回滚：删除 `/api/text/optimize` 路由不会影响原转写记录优化和 B 站处理接口。
- 已生成候选无需删除，可在候选审核页选择拒绝；当前文章始终未被自动修改。

## 遗留风险

- Radio 当前是同步 Gemini 调用，但运行在 AI Assist heavy worker 中并有 150 秒读取上限，不阻塞用户的 HTTP 提交请求。
- Radio 是正文轻量润色服务，不生成标题、摘要或分类；需要这些字段时应选择 AI Assist。
- Radio 和 AI Assist 都属于外部模型处理路径，敏感文章在选择前应确认符合使用预期。
