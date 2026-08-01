# 修复复盘：读者友好文章未生成流程图（2026-08-01）

## 现象

文章 `62de9f60-fe5e-4cb8-bf1a-ef1db4320091`（“SK Hynix IPO次日短线交易复盘：盈利150美元后的反思”）完成一次结构优化后，正文没有生成流程图或其他 PNG 视觉增强。

## 根因

该文章的优化运行已经自动识别为读者友好解释模式（`reader_explainer=true`），但本次运行类型为 `structure`，模型没有返回视觉增强项，验证结果中的 `visual_enhancements` 为空。

系统随后执行兜底逻辑，但当时只从“优化后的正文”提取流程节点。结构优化把原文的 Markdown 标题和列表转换成了粗体段落，兜底提取不到至少 3 个节点，于是没有生成 PNG。文章并非不适合流程图，问题出在视觉生成兜底对结构化格式变化不够稳健。

## 修改

- 视觉兜底仍优先读取优化后的正文。
- 如果优化结果丢失标题/列表结构，改为回退读取原始文章的 Markdown 结构。
- 只使用原文中可追溯的标题、列表或编号步骤生成紧凑流程图，不凭空补充事实。
- 保持候选审核流程：PNG 作为候选增强生成，需用户审核并应用后才改变文章当前版本。

代码提交：`568488d`；发布提交：`812182c`。

## 验证

1. 自动分类单元验证通过：读者友好文章无需额外提示词即可识别，节点数达到生成流程图所需的最小数量。
2. 水循环示例通过完整优化验证：自动识别读者模式，并生成 5 节点紧凑流程图资产。
3. 生产构建、数据库迁移、backend/frontend 健康检查以及 fast/heavy worker ping 均通过。
4. 修复目标文章的历史运行已确认：`reader_explainer=true`、`candidate_node_count=7`，但 `visual_enhancements=[]`，与上述根因一致。
5. 修复后需要对目标文章重新提交一次 AI Assist 全面优化，才能生成新的候选 PNG；已发布文章不会被后台静默覆盖。

## 日志检索方式

只检索文章 ID、AI 运行 ID、候选 ID、步骤和验证摘要，不输出 Cookie、令牌、Prompt 或正文：

```bash
docker compose logs --since=2h --no-color backend worker-fast worker-heavy \
  | rg '62de9f60-fe5e-4cb8-bf1a-ef1db4320091|reader_explainer|visual_enhancements|candidate_node_count|saving_candidate'
```

数据库/接口排查时只保留 `post_id`、`ai_run_id`、`candidate_id`、`optimization_type`、`validation_summary` 和 `status` 等业务字段。

## 遗留风险

- 如果文章完全没有 3 个以上可追溯的标题、列表或编号步骤，系统仍会跳过流程图，避免生成与原文不一致的内容。
- 模型返回视觉增强时仍需通过资产生成、Markdown 插入和候选审核链路；任一环节失败只能保留文字候选。
- 目标文章尚未在本次修复后重新运行，因此当前公开页面不会自动出现流程图；需要重新生成并审核应用候选。
