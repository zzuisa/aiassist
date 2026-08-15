<!-- SPECKIT START -->
For additional context about technologies, architecture, project structure,
contracts, and implementation constraints, read the current plan:
`specs/010-prompt-skill-management/plan.md`.
<!-- SPECKIT END -->

## 修复复盘归档

每次完成线上故障修复后：

1. 在 docs/fix-reports/ 创建一篇 Markdown 复盘，至少记录现象、根因、修改、验证、日志检索方式和遗留风险。
2. 使用 AI Assist 自身 API 创建文章，标题采用“修复复盘：主题（日期）”，分类统一使用“AI Assist 修复复盘”，形成连续合集。
3. 发布前不得写入密码、令牌、Cookie、私钥或其他密钥；只保留必要且安全的业务对象 ID。
4. API 归档默认保留为 AI Assist 内部文章，不执行公开发布，除非用户明确要求公开。
