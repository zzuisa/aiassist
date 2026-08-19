<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ApiError } from '@/api/client'
import {
  aiConfigApi,
  type AIConfigBinding,
  type AIConfigModule,
  type AIConfigModuleDetail,
} from '@/api/aiConfig'

const modules = ref<AIConfigModule[]>([])
const selectedKey = ref('conversation_route')
const detail = ref<AIConfigModuleDetail | null>(null)
const promptInstruction = ref('')
const skillName = ref('')
const skillInstruction = ref('')
const parameterDefaults = ref('{\n  "posts.list_recent": { "limit": 10 }\n}')
const message = ref('')
const error = ref('')
const saving = ref(false)
const dryRunInput = ref('查一下最近文章')
const dryRunResult = ref('')
const bindings = ref<AIConfigBinding[]>([])

const selectedPromptId = ref<string | null>(null)
const selectedSkillId = ref<string | null>(null)
const isArticleQuery = computed(() => selectedKey.value === 'conversation_route')

async function loadDetail(): Promise<void> {
  error.value = ''
  detail.value = await aiConfigApi.get(selectedKey.value)
  selectedPromptId.value = detail.value.active_prompt_version_id
  selectedSkillId.value = detail.value.active_skill_version_id
  const activePrompt = detail.value.prompt_versions.find(
    (version) => version.id === detail.value?.active_prompt_version_id,
  )
  const activeSkill = detail.value.skill_versions.find(
    (version) => version.id === detail.value?.active_skill_version_id,
  )
  promptInstruction.value = activePrompt?.instruction ?? detail.value.baseline_instruction
  skillName.value = activeSkill?.name ?? `${detail.value.title} 默认 Skill`
  skillInstruction.value = activeSkill?.instruction
    ?? '根据用户的自然语言请求选择合适工具，并使用以下默认参数。'
  parameterDefaults.value = JSON.stringify(
    activeSkill?.parameter_defaults
      ?? (isArticleQuery.value ? { 'posts.list_recent': { limit: 10 } } : {}),
    null,
    2,
  )
}

async function load(): Promise<void> {
  const [moduleRows, bindingRows] = await Promise.all([
    aiConfigApi.list(),
    aiConfigApi.listBindings(),
  ])
  modules.value = moduleRows
  bindings.value = bindingRows
  if (!modules.value.some((item) => item.key === selectedKey.value)) {
    selectedKey.value = modules.value[0]?.key ?? ''
  }
  if (selectedKey.value) await loadDetail()
}

watch(selectedKey, () => {
  if (selectedKey.value) void loadDetail().catch(displayError)
})

function displayError(err: unknown): void {
  error.value = err instanceof ApiError ? err.message : '操作失败，请稍后再试。'
}

async function savePrompt(): Promise<void> {
  if (!detail.value) return
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const version = await aiConfigApi.createPrompt(detail.value.key, { instruction: promptInstruction.value })
    selectedPromptId.value = version.id
    await activate()
    message.value = `已创建并启用 Prompt v${version.version_number}`
    await loadDetail()
  } catch (err) {
    displayError(err)
  } finally {
    saving.value = false
  }
}

async function saveSkill(): Promise<void> {
  if (!detail.value) return
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const defaults = JSON.parse(parameterDefaults.value) as Record<string, Record<string, unknown>>
    const version = await aiConfigApi.createSkill(detail.value.key, {
      name: skillName.value,
      instruction: skillInstruction.value,
      parameter_defaults: defaults,
    })
    selectedSkillId.value = version.id
    await activate()
    message.value = `已创建并启用 Skill v${version.version_number}`
    await loadDetail()
  } catch (err) {
    error.value = err instanceof SyntaxError ? '工具默认参数必须是合法 JSON。' : ''
    if (!error.value) displayError(err)
  } finally {
    saving.value = false
  }
}

async function activate(): Promise<void> {
  if (!detail.value) return
  try {
    await aiConfigApi.activate(detail.value.key, {
      prompt_version_id: selectedPromptId.value,
      skill_version_id: selectedSkillId.value,
    })
  } catch (err) {
    displayError(err)
    throw err
  }
}

async function activateExisting(): Promise<void> {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    await activate()
    message.value = '已切换生效版本'
    await loadDetail()
  } catch {
    // activate() already turns API failures into a user-visible message.
  } finally {
    saving.value = false
  }
}

async function runDryRun(): Promise<void> {
  if (!detail.value) return
  saving.value = true
  error.value = ''
  dryRunResult.value = ''
  try {
    const result = await aiConfigApi.dryRun(detail.value.key, dryRunInput.value)
    dryRunResult.value = JSON.stringify(result, null, 2)
    bindings.value = await aiConfigApi.listBindings()
  } catch (err) {
    displayError(err)
  } finally {
    saving.value = false
  }
}

onMounted(() => void load().catch(displayError))
</script>

<template>
  <section class="ai-config">
    <h1>AI 行为配置</h1>
    <p class="intro">
      为每个 AI 模块创建不可变版本，并选择当前生效的 Prompt 与 Skill。
    </p>

    <label class="field">
      <span>模块</span>
      <select v-model="selectedKey">
        <option
          v-for="item in modules"
          :key="item.key"
          :value="item.key"
        >{{ item.title }}</option>
      </select>
    </label>

    <template v-if="detail">
      <p class="boundary">
        {{ detail.safety_boundary }}
      </p>
      <p
        v-if="isArticleQuery"
        class="hint"
      >
        “查一下最近文章”会采用 Skill 中的 <code>posts.list_recent.limit</code> 默认值；用户明确说数量时，模型给出的数量优先。
      </p>

      <fieldset>
        <legend>Prompt 版本</legend>
        <label class="field"><span>系统指令</span><textarea
          v-model="promptInstruction"
          rows="8"
        /></label>
        <button
          type="button"
          class="primary"
          :disabled="saving"
          @click="savePrompt"
        >
          保存为新版本并启用
        </button>
      </fieldset>

      <fieldset>
        <legend>Skill 版本</legend>
        <label class="field"><span>名称</span><input v-model="skillName"></label>
        <label class="field"><span>指令</span><textarea
          v-model="skillInstruction"
          rows="3"
        /></label>
        <label class="field"><span>工具默认参数（JSON）</span><textarea
          v-model="parameterDefaults"
          rows="5"
          spellcheck="false"
        /></label>
        <p class="hint">
          允许的工具：{{ detail.allowed_tool_keys.join('、') || '此模块不调用工具' }}
        </p>
        <button
          type="button"
          class="primary"
          :disabled="saving"
          @click="saveSkill"
        >
          保存为新版本并启用
        </button>
      </fieldset>

      <fieldset>
        <legend>已保存版本</legend>
        <label class="field"><span>启用 Prompt</span><select v-model="selectedPromptId"><option :value="null">使用系统基线</option><option
          v-for="version in detail.prompt_versions"
          :key="version.id"
          :value="version.id"
        >v{{ version.version_number }}</option></select></label>
        <label class="field"><span>启用 Skill</span><select v-model="selectedSkillId"><option :value="null">使用系统基线</option><option
          v-for="version in detail.skill_versions"
          :key="version.id"
          :value="version.id"
        >v{{ version.version_number }} · {{ version.name }}</option></select></label>
        <button
          type="button"
          :disabled="saving"
          @click="activateExisting"
        >
          切换生效版本
        </button>
      </fieldset>

      <fieldset>
        <legend>安全试运行</legend>
        <label class="field"><span>样例输入</span><textarea
          v-model="dryRunInput"
          rows="3"
        /></label>
        <p class="hint">
          试运行只解析并校验配置，不执行工具，也不会修改文章、待办或其他业务数据。
        </p>
        <button
          type="button"
          :disabled="saving || !dryRunInput.trim()"
          @click="runDryRun"
        >
          运行测试
        </button>
        <pre v-if="dryRunResult">{{ dryRunResult }}</pre>
      </fieldset>

      <fieldset>
        <legend>最近运行绑定</legend>
        <p
          v-if="bindings.length === 0"
          class="hint"
        >
          暂无运行记录。
        </p>
        <ol v-else>
          <li
            v-for="binding in bindings.slice(0, 10)"
            :key="binding.id"
          >
            {{ binding.module_key }} · Prompt {{ binding.prompt_version_id || '基线' }} · Skill {{ binding.skill_version_id || '基线' }}
          </li>
        </ol>
      </fieldset>
    </template>

    <p
      v-if="message"
      class="ok"
    >
      {{ message }}
    </p>
    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.ai-config { max-width: 760px; margin: 0 auto; padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-4); }
.intro, .hint, .boundary { margin: 0; color: var(--color-text-muted); }
.boundary { padding: var(--space-2); border-left: 3px solid var(--status-normal); background: var(--color-surface); }
fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
legend { color: var(--color-text-muted); padding: 0 var(--space-2); }
.field { display: flex; flex-direction: column; gap: 4px; }
input, select, textarea { box-sizing: border-box; width: 100%; padding: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font: inherit; }
textarea { resize: vertical; }
pre { overflow: auto; margin: 0; padding: var(--space-2); border-radius: var(--radius-sm); background: var(--color-surface); white-space: pre-wrap; }
ol { margin: 0; padding-left: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
button { min-height: var(--tap-target); padding: 0 var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); cursor: pointer; }
button.primary { background: var(--status-normal); color: white; border: none; }
button:disabled { opacity: .55; cursor: default; }
.ok { color: var(--status-done); }.error { color: var(--status-urgent); } code { font-family: ui-monospace, monospace; }
</style>
