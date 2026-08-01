<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '@/api/client'
import {
  blogSettingsApi,
  type BlogSettings,
  type AiApplySettings,
} from '@/api/blogSettings'

type Section = 'create_defaults' | 'clipboard' | 'url_capture' | 'ai_apply' | 'word_cloud'
const sections: Array<{ key: Section; label: string }> = [
  { key: 'create_defaults', label: '默认创建' },
  { key: 'clipboard', label: '剪切板' },
  { key: 'url_capture', label: 'URL' },
  { key: 'ai_apply', label: 'AI 结果' },
  { key: 'word_cloud', label: '词云' },
]
const settings = ref<BlogSettings | null>(null)
const baseline = ref<BlogSettings | null>(null)
const active = ref<Section>('create_defaults')
const status = ref('')
const saving = ref(false)
const excludeTerms = ref('')
const excludedClasses = ref('')

const defaults: Record<Section, Record<string, unknown>> = {
  create_defaults: {
    content_class: 'essay', language: 'zh-CN', content_type_id: null, category_id: null,
    tag_ids: [], status: 'draft', editor_mode: 'rich', ai_enabled: false,
    default_skill_id: null, model: null, generate_summary: true, generate_keywords: true,
    recommend_tags: true, retain_original: true,
  },
  clipboard: {
    enabled: true, auto_parse: false, default_content_class: 'quick', cleanup_format: true,
    retain_original: true, detect_urls: true, auto_ai: false, default_skill_id: null,
  },
  url_capture: {
    enabled: true, auto_fetch_title: true, auto_extract_body: false,
    default_content_class: 'bookmark', retain_original: true, retain_snapshot: false,
    extract_images: false, auto_ai: false, default_skill_id: null,
  },
  ai_apply: {
    confirm_before_apply: true, default_fields: ['title', 'markdown'], show_diff: true,
    default_provider: 'radio', allow_auto_apply: false, auto_apply_fields: [],
    confirm_fields: ['markdown', 'content_class', 'language', 'structured_data'],
    merge_on_version_change: true, retain_job_history: true,
  },
  word_cloud: {
    enabled: true, min_term_count: 2, max_terms: 100, exclude_terms: [],
    excluded_content_classes: [],
  },
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
function syncLists(): void {
  if (!settings.value) return
  excludeTerms.value = settings.value.word_cloud.exclude_terms.join('，')
  excludedClasses.value = settings.value.word_cloud.excluded_content_classes.join('，')
}
async function load(): Promise<void> {
  settings.value = await blogSettingsApi.get()
  baseline.value = clone(settings.value)
  syncLists()
}
onMounted(() => void load())

const impactSummary = computed(() => {
  if (!settings.value || !baseline.value) return ''
  const notes: string[] = []
  if (settings.value.create_defaults.ai_enabled !== baseline.value.create_defaults.ai_enabled) {
    notes.push('将改变后续新建文章是否自动提交 AI 任务')
  }
  if (settings.value.clipboard.auto_ai !== baseline.value.clipboard.auto_ai
    || settings.value.url_capture.auto_ai !== baseline.value.url_capture.auto_ai) {
    notes.push('将改变后续采集是否自动提交 AI 任务')
  }
  if (settings.value.ai_apply.allow_auto_apply) {
    notes.push('允许字段自动应用；正文仍被强制排除')
  }
  return notes.join('；')
})

function restoreSection(): void {
  if (!settings.value) return
  Object.assign(settings.value[active.value], clone(defaults[active.value]))
  syncLists()
  status.value = '已恢复本组安全默认值，保存后生效。'
}
function toggleAiField(field: string, checked: boolean): void {
  if (!settings.value) return
  const policy: AiApplySettings = settings.value.ai_apply
  policy.auto_apply_fields = checked
    ? [...policy.auto_apply_fields, field]
    : policy.auto_apply_fields.filter((item) => item !== field)
  policy.confirm_fields = policy.confirm_fields.filter((item) => item !== field)
}
function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean))]
}
async function save(): Promise<void> {
  if (!settings.value) return
  settings.value.word_cloud.exclude_terms = splitTerms(excludeTerms.value)
  settings.value.word_cloud.excluded_content_classes = splitTerms(excludedClasses.value)
  saving.value = true
  status.value = ''
  try {
    settings.value = await blogSettingsApi.update(settings.value)
    baseline.value = clone(settings.value)
    syncLists()
    status.value = '博客设置已保存；不会回写历史文章或已提交任务。'
  } catch (error) {
    status.value = error instanceof ApiError && error.status === 409
      ? '设置已被其他会话修改，请刷新后重试。'
      : '设置校验失败，请检查当前分组。'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="settings-page">
    <header>
      <div>
        <p class="eyebrow">
          博客模块
        </p><h1>博客设置</h1>
      </div>
      <button
        :disabled="saving || !settings"
        class="primary"
        @click="save"
      >
        {{ saving ? '保存中…' : '保存全部' }}
      </button>
    </header>
    <p
      v-if="!settings"
      role="status"
    >
      正在加载设置…
    </p>
    <template v-else>
      <nav aria-label="博客设置分组">
        <button
          v-for="section in sections"
          :key="section.key"
          :class="{ active: active === section.key }"
          :aria-current="active === section.key ? 'page' : undefined"
          @click="active = section.key"
        >
          {{ section.label }}
        </button>
      </nav>

      <section
        v-if="active === 'create_defaults'"
        aria-labelledby="create-title"
      >
        <h2 id="create-title">
          默认创建
        </h2>
        <label>文章大类<input v-model="settings.create_defaults.content_class"></label>
        <label>语言<input v-model="settings.create_defaults.language"></label>
        <label>编辑模式<select v-model="settings.create_defaults.editor_mode"><option value="rich">富文本</option><option value="markdown">Markdown</option></select></label>
        <label><input
          v-model="settings.create_defaults.ai_enabled"
          type="checkbox"
        >新建后提交 AI 优化</label>
        <label><input
          v-model="settings.create_defaults.generate_summary"
          type="checkbox"
        >生成摘要</label>
        <label><input
          v-model="settings.create_defaults.generate_keywords"
          type="checkbox"
        >生成关键词</label>
        <label><input
          v-model="settings.create_defaults.recommend_tags"
          type="checkbox"
        >推荐标签</label>
        <label><input
          v-model="settings.create_defaults.retain_original"
          type="checkbox"
        >保留原始内容</label>
      </section>

      <section
        v-else-if="active === 'clipboard'"
        aria-labelledby="clipboard-title"
      >
        <h2 id="clipboard-title">
          剪切板
        </h2>
        <label><input
          v-model="settings.clipboard.cleanup_format"
          type="checkbox"
        >清理粘贴格式</label>
        <label><input
          v-model="settings.clipboard.retain_original"
          type="checkbox"
        >保留原始剪切板</label>
        <label><input
          v-model="settings.clipboard.detect_urls"
          type="checkbox"
        >识别内容中的 URL</label>
        <label><input
          v-model="settings.clipboard.auto_ai"
          type="checkbox"
        >创建后自动提交 AI</label>
        <label>默认 Skill ID<input v-model="settings.clipboard.default_skill_id"></label>
      </section>

      <section
        v-else-if="active === 'url_capture'"
        aria-labelledby="url-title"
      >
        <h2 id="url-title">
          URL 采集
        </h2>
        <label><input
          v-model="settings.url_capture.retain_original"
          type="checkbox"
        >保留原文</label>
        <label><input
          v-model="settings.url_capture.retain_snapshot"
          type="checkbox"
        >保留网页快照</label>
        <label><input
          v-model="settings.url_capture.extract_images"
          type="checkbox"
        >提取图片</label>
        <label><input
          v-model="settings.url_capture.auto_ai"
          type="checkbox"
        >提取后自动提交 AI</label>
        <label>默认文章大类<input v-model="settings.url_capture.default_content_class"></label>
        <label>默认 Skill ID<input v-model="settings.url_capture.default_skill_id"></label>
      </section>

      <section
        v-else-if="active === 'ai_apply'"
        aria-labelledby="ai-title"
      >
        <h2 id="ai-title">
          AI 结果
        </h2>
        <label><input
          v-model="settings.ai_apply.allow_auto_apply"
          type="checkbox"
        >允许安全字段自动应用</label>
        <fieldset :disabled="!settings.ai_apply.allow_auto_apply">
          <legend>可自动应用字段</legend>
          <label
            v-for="field in ['title', 'subtitle', 'summary']"
            :key="field"
          >
            <input
              type="checkbox"
              :checked="settings.ai_apply.auto_apply_fields.includes(field)"
              @change="toggleAiField(field, ($event.target as HTMLInputElement).checked)"
            >{{ field }}
          </label>
        </fieldset>
        <p>正文、分类、语言和结构化字段始终需要确认；版本变化时强制进入合并。</p>
        <label><input
          v-model="settings.ai_apply.merge_on_version_change"
          type="checkbox"
          disabled
        >版本变化时强制待合并</label>
        <label><input
          v-model="settings.ai_apply.retain_job_history"
          type="checkbox"
        >保留任务历史</label>
      </section>

      <section
        v-else
        aria-labelledby="cloud-title"
      >
        <h2 id="cloud-title">
          词云
        </h2>
        <p>设置只用于下一次手动重建，不会进入文章保存路径。</p>
        <label><input
          v-model="settings.word_cloud.enabled"
          type="checkbox"
        >启用词云探索入口</label>
        <label>最低出现频次<input
          v-model.number="settings.word_cloud.min_term_count"
          type="number"
          min="1"
          max="100000"
        ></label>
        <label>最多展示词数<input
          v-model.number="settings.word_cloud.max_terms"
          type="number"
          min="1"
          max="500"
        ></label>
        <label>排除词<textarea
          v-model="excludeTerms"
          placeholder="逗号或换行分隔"
        /></label>
        <label>排除文章大类<textarea
          v-model="excludedClasses"
          placeholder="逗号或换行分隔"
        /></label>
        <RouterLink to="/blog/word-cloud">
          前往词云并手动重建 →
        </RouterLink>
      </section>

      <aside
        v-if="impactSummary"
        class="impact"
        role="note"
      >
        <strong>保存影响：</strong>{{ impactSummary }}。只影响后续操作。
      </aside>
      <ul
        v-if="settings.warnings.length"
        class="warnings"
        aria-label="设置警告"
      >
        <li
          v-for="warning in settings.warnings"
          :key="warning"
        >
          {{ warning }}
        </li>
      </ul>
      <footer>
        <button @click="restoreSection">
          恢复本组默认
        </button>
        <p
          v-if="status"
          role="status"
        >
          {{ status }}
        </p>
      </footer>
    </template>
  </main>
</template>

<style scoped>
.settings-page{max-width:840px;margin:auto;padding:var(--space-4)}header,footer{display:flex;justify-content:space-between;align-items:center;gap:var(--space-3)}h1,.eyebrow{margin:0}.eyebrow{color:var(--color-text-muted)}nav{display:flex;gap:var(--space-2);overflow:auto;margin:var(--space-4) 0;border-bottom:1px solid var(--color-border)}nav button{white-space:nowrap;border:0;border-bottom:3px solid transparent;background:transparent}nav .active{border-color:var(--status-normal)}section{display:grid;gap:var(--space-3);padding:var(--space-4);border:1px solid var(--color-border);border-radius:var(--radius-lg)}label{display:grid;gap:var(--space-1)}label:has(input[type="checkbox"]){display:flex;align-items:center}input,select,textarea,button{min-height:var(--tap-target);padding:var(--space-2)}textarea{min-height:5rem}.primary{background:var(--status-normal);color:#fff;border:0;border-radius:var(--radius-sm)}.impact,.warnings{margin:var(--space-3) 0;padding:var(--space-3);border-radius:var(--radius-sm);background:var(--color-surface-muted)}@media(max-width:480px){header{align-items:flex-start}section{padding:var(--space-3)}}
</style>
