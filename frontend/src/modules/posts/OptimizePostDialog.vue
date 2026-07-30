<script setup lang="ts">
// AI optimize dialog (spec 005, US3, T078).
//
// Submits an async optimization bound to the *current* revision. The AI never
// mutates the live article; it produces an unapplied candidate reviewed later
// (US4). The advanced panel exposes optimization type, scope, optional
// selected fields, Skill and model overrides, and a free-text instruction —
// all optional: leaving Skill/model empty lets the server resolve defaults.
import { computed, onMounted, ref } from 'vue'
import {
  blogAIApi,
  classifyOptimizeError,
  type OptimizationScope,
  type OptimizationType,
} from '@/api/blogAI'
import { blogSkillsApi, type Skill } from '@/api/blogSkills'
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const props = defineProps<{ postId: string; postVersion: number }>()
const emit = defineEmits<{
  (e: 'close'): void
  // Emitted with the submitted Job id so the caller can follow status.
  (e: 'submitted', jobId: string): void
}>()

const typeOptions: Array<{ value: OptimizationType; label: string }> = [
  { value: 'full', label: '全面优化' },
  { value: 'language', label: '语言润色' },
  { value: 'structure', label: '结构梳理' },
  { value: 'metadata', label: '元数据补全' },
  { value: 'check', label: '仅检查（不改写）' },
  { value: 'reoptimize', label: '重新优化' },
]

const scopeOptions: Array<{ value: OptimizationScope; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'body', label: '仅正文' },
  { value: 'metadata', label: '仅元数据' },
  { value: 'selected_fields', label: '指定字段' },
]

const optimizationType = ref<OptimizationType>('full')
const scope = ref<OptimizationScope>('all')
const selectedFieldsText = ref('')
const skillId = ref('')
const modelKey = ref('')
const instruction = ref('')
const advanced = ref(false)

// Available enabled Skills so the user can pick one instead of typing an id;
// empty selection means "let the server resolve the default for this article".
const skills = ref<Skill[]>([])
onMounted(async () => {
  try {
    skills.value = (await blogSkillsApi.list()).filter((s) => s.enabled && s.current_version_complete)
  } catch {
    skills.value = []
  }
})

const busy = ref(false)
const error = ref('')

const selectedFields = computed(() =>
  selectedFieldsText.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean),
)

const canSubmit = computed(
  () =>
    !busy.value &&
    (scope.value !== 'selected_fields' || selectedFields.value.length > 0),
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ''
  try {
    const job = await blogAIApi.optimize(props.postId, {
      post_version: props.postVersion,
      optimization_type: optimizationType.value,
      scope: scope.value,
      selected_fields: scope.value === 'selected_fields' ? selectedFields.value : [],
      skill_id: skillId.value.trim() || null,
      model_key: modelKey.value.trim() || null,
      instruction: instruction.value.trim() || null,
    })
    emit('submitted', job.id)
  } catch (e) {
    const kind = classifyOptimizeError(e)
    error.value =
      kind === 'version_conflict'
        ? '文章已被修改，请重新载入后再优化。'
        : kind === 'skill_unresolved'
          ? '未找到可用的 Skill 配置，请先在设置中配置或指定 Skill。'
          : kind === 'invalid_request'
            ? '请求参数不正确，请检查所选字段。'
            : kind === 'not_found'
              ? '文章不存在或无权访问。'
              : '提交失败，请稍后重试。'
    busy.value = false
  }
}
</script>

<template>
  <CaptureModal
    title="AI 优化"
    :busy="busy"
    @close="emit('close')"
  >
    <label class="field">
      <span>优化类型</span>
      <select
        v-model="optimizationType"
        aria-label="优化类型"
        :disabled="busy"
      >
        <option
          v-for="o in typeOptions"
          :key="o.value"
          :value="o.value"
        >
          {{ o.label }}
        </option>
      </select>
    </label>

    <label class="field">
      <span>范围</span>
      <select
        v-model="scope"
        aria-label="范围"
        :disabled="busy"
      >
        <option
          v-for="o in scopeOptions"
          :key="o.value"
          :value="o.value"
        >
          {{ o.label }}
        </option>
      </select>
    </label>

    <label
      v-if="scope === 'selected_fields'"
      class="field"
    >
      <span>指定字段（逗号或空格分隔）</span>
      <input
        v-model="selectedFieldsText"
        aria-label="指定字段"
        placeholder="title, summary, structured_data.city"
        :disabled="busy"
      >
    </label>

    <button
      type="button"
      class="advanced-toggle"
      :aria-expanded="advanced"
      @click="advanced = !advanced"
    >
      {{ advanced ? '▾ 收起高级选项' : '▸ 高级选项（Skill / 模型 / 指令）' }}
    </button>

    <div
      v-if="advanced"
      class="advanced"
    >
      <label class="field">
        <span>Skill（可选，留空按内容类别自动匹配默认）</span>
        <select
          v-model="skillId"
          aria-label="Skill"
          :disabled="busy"
        >
          <option value="">
            （自动匹配默认）
          </option>
          <option
            v-for="s in skills"
            :key="s.id"
            :value="s.id"
          >
            {{ s.name }}
          </option>
        </select>
      </label>
      <label class="field">
        <span>模型（可选，留空使用默认）</span>
        <input
          v-model="modelKey"
          aria-label="模型"
          placeholder="model key"
          :disabled="busy"
        >
      </label>
      <label class="field">
        <span>附加指令（可选）</span>
        <textarea
          v-model="instruction"
          rows="2"
          aria-label="附加指令"
          placeholder="例如：保留所有代码块和命令，语气更正式"
          :disabled="busy"
        />
      </label>
    </div>

    <p class="hint">
      优化在后台运行，不会改动当前文章；完成后会生成待审核的候选版本。
    </p>

    <p
      v-if="error"
      class="opt-error"
      role="alert"
    >
      {{ error }}
    </p>

    <template #footer>
      <button
        type="button"
        class="ghost"
        :disabled="busy"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        type="button"
        class="primary"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ busy ? '提交中…' : '开始优化' }}
      </button>
    </template>
  </CaptureModal>
</template>

<style scoped>
.field {
  display: block;
  margin-bottom: var(--space-3);
}
.field > span {
  display: block;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.25rem;
}
.field input,
.field textarea,
.field select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.advanced-toggle {
  border: none;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0;
  margin-bottom: var(--space-3);
  font: inherit;
}
.advanced {
  padding: var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-3);
}
.hint {
  margin: 0 0 var(--space-2);
  font-size: 0.85rem;
  color: var(--color-text-muted);
}
.opt-error {
  color: var(--status-danger, #dc2626);
  margin: 0;
  font-size: 0.9rem;
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: none;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
