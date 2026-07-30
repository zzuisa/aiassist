<script setup lang="ts">
// Skill editor (spec 005, US5, T107).
//
// Sectioned editor over blog-skill-config.v1. Editing an existing Skill saves an
// immutable NEW version (never mutates history). A per-field policy table decides
// how each field may be applied. The content-size safety ceiling is enforced
// client-side (≤ 200000) with a clear error, and an impact summary states that
// saving creates a new current version.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  blogSkillsApi,
  type FieldPolicy,
  type LongContentStrategy,
  type SkillConfig,
} from '@/api/blogSkills'

const route = useRoute()
const router = useRouter()
const skillId = computed(() => (route.params.skillId as string) || null)
const isNew = computed(() => skillId.value === null)

const SAFETY_CEILING = 200_000
const POLICY_FIELDS = ['title', 'subtitle', 'summary', 'markdown', 'content_class'] as const
const POLICIES: FieldPolicy[] = [
  'forbid', 'suggest_only', 'require_confirmation', 'fill_if_empty',
  'auto_fill', 'allow_overwrite', 'keep_both_on_conflict',
]
const STRATEGIES: LongContentStrategy[] = ['reject', 'chunk', 'summarize_then_process']

const name = ref('')
const description = ref('')
const goal = ref('')
const contentClasses = ref('essay, technical, life')
const contentRules = ref('')
const titleRules = ref('')
const summaryRules = ref('')
const bodyStructure = ref('')
const prohibitions = ref('禁止编造事实')
const outputFields = ref('title\nsummary\nmarkdown')
const fieldPolicies = ref<Record<string, FieldPolicy>>({
  title: 'suggest_only', summary: 'fill_if_empty', markdown: 'require_confirmation',
})
const maxChars = ref(SAFETY_CEILING)
const strategy = ref<LongContentStrategy>('reject')
const changeSummary = ref('')

const busy = ref(false)
const error = ref('')

const overCeiling = computed(() => maxChars.value > SAFETY_CEILING || maxChars.value < 1000)

function lines(v: string): string[] {
  return v.split('\n').map((l) => l.trim()).filter(Boolean)
}
function csv(v: string): string[] {
  return v.split(/[,，]/).map((l) => l.trim()).filter(Boolean)
}

async function load(): Promise<void> {
  if (isNew.value) return
  const skill = await blogSkillsApi.get(skillId.value!)
  name.value = skill.name
  description.value = skill.description ?? ''
  const c = skill.current_version?.config
  if (c) {
    goal.value = c.processing_goal
    contentClasses.value = c.applicable_content_classes.join(', ')
    contentRules.value = c.content_rules.join('\n')
    titleRules.value = c.title_rules.join('\n')
    summaryRules.value = c.summary_rules.join('\n')
    bodyStructure.value = c.body_structure.join('\n')
    prohibitions.value = c.prohibitions.join('\n')
    outputFields.value = c.output_fields.join('\n')
    fieldPolicies.value = { ...c.field_policies }
    maxChars.value = c.max_content_chars
    strategy.value = c.long_content_strategy
  }
}

function buildConfig(): SkillConfig {
  return {
    schema_version: 'blog-skill-config.v1',
    applicable_content_classes: csv(contentClasses.value),
    applicable_content_type_ids: [],
    processing_goal: goal.value.trim(),
    content_rules: lines(contentRules.value),
    title_rules: lines(titleRules.value),
    summary_rules: lines(summaryRules.value),
    body_structure: lines(bodyStructure.value),
    taxonomy_rules: [],
    keyword_rules: [],
    prohibitions: lines(prohibitions.value),
    field_policies: fieldPolicies.value,
    output_fields: lines(outputFields.value),
    output_schema: 'blog-optimization.v1',
    validation_rules: [],
    recommended_model: null,
    max_content_chars: maxChars.value,
    long_content_strategy: strategy.value,
  }
}

async function save(): Promise<void> {
  error.value = ''
  if (!name.value.trim()) {
    error.value = '请填写技能名称。'
    return
  }
  if (overCeiling.value) {
    error.value = `内容上限必须在 1000 到 ${SAFETY_CEILING} 之间。`
    return
  }
  if (!goal.value.trim()) {
    error.value = '请填写处理目标。'
    return
  }
  if (lines(prohibitions.value).length === 0 || lines(outputFields.value).length === 0) {
    error.value = '禁止项与输出字段至少各填一项。'
    return
  }
  busy.value = true
  try {
    const config = buildConfig()
    if (isNew.value) {
      const skill = await blogSkillsApi.create({ name: name.value.trim(), description: description.value, config })
      router.push({ name: 'blog-skill-edit', params: { skillId: skill.id } })
    } else {
      await blogSkillsApi.updateMeta(skillId.value!, { name: name.value.trim(), description: description.value })
      await blogSkillsApi.addVersion(skillId.value!, { config, change_summary: changeSummary.value || null })
      router.push({ name: 'blog-skills-list' })
    }
  } catch {
    error.value = '保存失败，请检查配置后重试。'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="editor">
    <header class="head">
      <h1>{{ isNew ? '新建技能' : '编辑技能' }}</h1>
      <RouterLink
        class="back"
        :to="{ name: 'blog-skills-list' }"
      >
        返回列表
      </RouterLink>
    </header>

    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>

    <fieldset>
      <legend>基本</legend>
      <label class="field"><span>名称</span>
        <input
          v-model="name"
          aria-label="名称"
        ></label>
      <label class="field"><span>描述</span>
        <input
          v-model="description"
          aria-label="描述"
        ></label>
      <label class="field"><span>处理目标</span>
        <textarea
          v-model="goal"
          rows="2"
          aria-label="处理目标"
        /></label>
      <label class="field"><span>适用内容类别（逗号分隔）</span>
        <input
          v-model="contentClasses"
          aria-label="适用内容类别"
        ></label>
    </fieldset>

    <fieldset>
      <legend>规则（每行一条）</legend>
      <label class="field"><span>正文规则</span><textarea
        v-model="contentRules"
        rows="3"
      /></label>
      <label class="field"><span>标题规则</span><textarea
        v-model="titleRules"
        rows="2"
      /></label>
      <label class="field"><span>摘要规则</span><textarea
        v-model="summaryRules"
        rows="2"
      /></label>
      <label class="field"><span>正文结构</span><textarea
        v-model="bodyStructure"
        rows="2"
      /></label>
      <label class="field"><span>禁止项</span><textarea
        v-model="prohibitions"
        rows="2"
        aria-label="禁止项"
      /></label>
      <label class="field"><span>输出字段</span><textarea
        v-model="outputFields"
        rows="2"
        aria-label="输出字段"
      /></label>
    </fieldset>

    <fieldset>
      <legend>字段应用策略</legend>
      <table class="policy">
        <thead>
          <tr><th>字段</th><th>策略</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="f in POLICY_FIELDS"
            :key="f"
          >
            <td>{{ f }}</td>
            <td>
              <select
                v-model="fieldPolicies[f]"
                :aria-label="`${f} 策略`"
              >
                <option
                  v-for="p in POLICIES"
                  :key="p"
                  :value="p"
                >
                  {{ p }}
                </option>
              </select>
            </td>
          </tr>
        </tbody>
      </table>
    </fieldset>

    <fieldset>
      <legend>长文本与安全上限</legend>
      <label class="field"><span>内容上限（字符，≤ {{ SAFETY_CEILING }}）</span>
        <input
          v-model.number="maxChars"
          type="number"
          aria-label="内容上限"
        ></label>
      <p
        v-if="overCeiling"
        class="err"
      >
        超出安全上限：必须在 1000 到 {{ SAFETY_CEILING }} 之间。
      </p>
      <label class="field"><span>长文本策略</span>
        <select
          v-model="strategy"
          aria-label="长文本策略"
        >
          <option
            v-for="s in STRATEGIES"
            :key="s"
            :value="s"
          >{{ s }}</option>
        </select></label>
      <label
        v-if="!isNew"
        class="field"
      ><span>本次修改说明</span>
        <input
          v-model="changeSummary"
          aria-label="修改说明"
        ></label>
    </fieldset>

    <p class="impact">
      {{ isNew ? '将创建一个新技能及其第 1 个版本。' : '保存将创建一个新的当前版本，历史版本保持不变。' }}
    </p>

    <div class="actions">
      <button
        type="button"
        class="primary"
        :disabled="busy || overCeiling"
        @click="save"
      >
        {{ busy ? '保存中…' : '保存' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.editor {
  padding: var(--space-4);
  max-width: 760px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.head h1 {
  font-size: 1.2rem;
  margin: 0;
}
.back {
  color: var(--color-text-muted);
  text-decoration: none;
}
.err {
  color: var(--status-danger, #dc2626);
}
fieldset {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin: var(--space-3) 0;
  padding: var(--space-3);
}
legend {
  font-weight: 600;
  padding: 0 0.35rem;
}
.field {
  display: block;
  margin-bottom: var(--space-2);
}
.field > span {
  display: block;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.2rem;
}
.field input,
.field textarea,
.field select {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.policy {
  width: 100%;
  border-collapse: collapse;
}
.policy th,
.policy td {
  text-align: left;
  padding: 0.35rem;
  border-bottom: 1px solid var(--color-border);
}
.policy select {
  width: 100%;
  padding: 0.25rem;
}
.impact {
  color: var(--color-text-muted);
  margin: var(--space-3) 0;
}
.primary {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: #fff;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
