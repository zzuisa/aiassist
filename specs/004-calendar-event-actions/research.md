# Research: 日历事件快捷操作与视觉优化

## 1. 完成与重要状态建模

**Decision**: 复用现有 `Task.status`、`completed_at` 和 `importance`。完成切换使用
`completed ↔ todo`；重要切换使用 `importance=4 ↔ 0`，展示判断为 `importance > 0`。

**Rationale**: 当前模型、API 乐观锁、活动日志、Today/Task store 已支持这些字段。复用可保持跨视图
一致，不引入两个可能漂移的状态来源。

**Alternatives considered**:

- 新增 `is_completed`/`is_important`：与既有字段重复并产生迁移与同步风险。
- 新建事件状态表：对两个简单用户状态过度设计。

## 2. 已完成事件的周日历可见性

**Decision**: 周视图的已排期 events 包含 completed，未排期列表仍只包含 todo/in_progress；cancelled
继续不展示。

**Rationale**: 当前 `get_week()` 先过滤开放状态，导致刚完成的事件从日历消失，无法显示用户要求的
emoji。按“已排期事件”和“未排期待办”分别查询可保留原有未排期行为。

**Alternatives considered**:

- 仅在前端保留已完成事件：刷新后消失且不是数据库真相。
- 把 completed 也放入未排期区：增加无关噪声并改变现有产品语义。

## 3. 重要提醒锚点与幂等性

**Decision**: 在现有 Reminder 上增加 `purpose` 与 `anchor`，用唯一用途
`important_start_4h` 表示从 `Task.start_at` 提前 240 分钟的 critical email 提醒；同一任务只复用
一条该用途记录。

**Rationale**: 现有 Reminder、每分钟扫描、Outbox、critical queue、邮件 Gateway 和投递记录已经覆盖
可靠发送，但当前 offset 重算锚定 `due_at` 且幂等键含触发时间。显式用途/锚点能在事件移动时更新
同一记录，避免重复邮件。

**Alternatives considered**:

- 每次重要切换直接创建普通 reminder：时间变化后容易留下旧提醒。
- Celery ETA 任务：调度状态不持久，重启和取消语义较弱。
- 新建独立 important_reminders 表：复制现有提醒生命周期和投递逻辑。

## 4. 事件备注模型

**Decision**: 每个 Task 最多一条 `TaskNote`，使用独立文字、版本和所有权字段；不复用
`Task.description`。

**Rationale**: Task.description 是事件自身描述，而 popover 备注是可持续追加图片的独立用户内容。
一对一结构满足当前单一“添加备注”入口，又为附件提供稳定父记录。

**Alternatives considered**:

- 复用 Task.description：无法清晰表达附件所有权和备注版本。
- 支持多条评论式备注：超出本次单一事件备注需求。

## 5. 图片附件与上传批次

**Decision**: 新增 `TaskNoteAsset`，每个成功上传文件一条记录；批次只是客户端上传动作，不建立持久
业务分组。上传会话新增 `task_note_image` purpose，后续批次逐张追加关联；过期且未关联的该用途
上传由既有 maintenance Worker 的新增清理步骤回收。

**Rationale**: 用户要求“多组图片”的核心是多次追加不覆盖。逐文件关联天然支持部分成功、单项重试
和准确归属；无需为批次创造用户看不到的新实体。限定 purpose 的过期清理可补偿“对象完成但业务
关联失败”的边界，而不会误删已经关联的附件。

**Alternatives considered**:

- 复用 Capture/CaptureAsset：会把事件附件污染到收藏业务并引入错误生命周期。
- 仅保存 upload_id 数组：缺乏稳定元数据、顺序、处理状态和安全访问边界。
- 新建上传批次表：当前没有命名、排序或批次级编辑需求。

## 6. 图片显示与隐私

**Decision**: 原图私有保存；关联提交后通过 Outbox 异步生成去除定位元数据的 WebP 预览。UI 默认
只访问预览，原图仅通过显式授权下载。

**Rationale**: 符合“内容先保存”和 Constitution 的派生图隐私要求，同时避免大原图拖慢日历 popover。
处理失败不影响原图、备注或其他附件，用户可看到失败并重试。

**Alternatives considered**:

- 同步生成预览：把耗时图片处理放入保存关键路径。
- 直接在浏览器显示原图：可能泄露定位元数据并浪费带宽。
- 重构成全局通用 MediaAsset：长期可能有价值，但对本功能范围过大。

## 7. FullCalendar 交互与视觉层级

**Decision**: 使用 `eventClick` 打开手动控制的 Vue popover；使用 event content slot 输出“标题在上、
时间在下”；使用 slot class hook 标识过去时间；通过语义 token 组合完成 emoji 与重要背景。

**Rationale**: 这些都是 FullCalendar 既有扩展点，可与当前 drag/resize 同页共存，并能在 Vue 组件中
保持安全转义、键盘焦点和移动端可见区域控制。

**Alternatives considered**:

- 修改 FullCalendar 生成的 DOM：升级脆弱且不利于可访问性。
- 点击后跳转详情页：不符合用户要求的就地 popover。
- 用颜色区分完成状态：违反语义颜色要求，且用户明确要求 emoji。
