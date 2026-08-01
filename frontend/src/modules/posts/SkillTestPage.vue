<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { blogSkillsApi, type Skill } from '@/api/blogSkills'
import type { AsyncJob } from '@/api/types'

const route = useRoute()
const skillId = computed(() => String(route.params.skillId))
const skill = ref<Skill | null>(null)
const title = ref('技能测试样例')
const markdown = ref('')
const instruction = ref('')
const job = ref<AsyncJob | null>(null)
const busy = ref(false)
const error = ref('')
let pollTimer: ReturnType<typeof setTimeout> | undefined

const terminal = computed(() => ['completed', 'failed', 'cancelled'].includes(job.value?.status ?? ''))
const result = computed(() => job.value?.result as Record<string, unknown> | null | undefined)
const candidate = computed(() => result.value?.candidate as Record<string, unknown> | undefined)
const validation = computed(() => result.value?.validation as Record<string, unknown> | undefined)

async function load(): Promise<void> {
  skill.value = await blogSkillsApi.get(skillId.value)
}

async function poll(jobId: string): Promise<void> {
  job.value = await blogSkillsApi.getDryRunJob(jobId)
  if (!terminal.value) pollTimer = setTimeout(() => void poll(jobId), 1000)
}

async function run(): Promise<void> {
  if (busy.value || !markdown.value.trim()) return
  busy.value = true
  error.value = ''
  job.value = null
  if (pollTimer) clearTimeout(pollTimer)
  try {
    const created = await blogSkillsApi.dryRun(skillId.value, {
      title: title.value,
      markdown: markdown.value,
      instruction: instruction.value || null,
    })
    job.value = created
    await poll(created.id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '技能测试提交失败'
  } finally {
    busy.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>

<template>
  <section class="skill-test">
    <header>
      <div>
        <h1>测试技能<span v-if="skill">：{{ skill.name }}</span></h1>
        <p>使用临时样例验证输出；不会创建或修改文章。</p>
      </div>
      <RouterLink :to="{ name: 'blog-skills-list' }">
        返回技能
      </RouterLink>
    </header>

    <label>样例标题<input
      v-model="title"
      aria-label="样例标题"
      maxlength="240"
    ></label>
    <label>样例正文<textarea
      v-model="markdown"
      aria-label="样例正文"
      rows="10"
      placeholder="粘贴一段用于测试的内容"
    /></label>
    <label>附加要求（可选）<textarea
      v-model="instruction"
      aria-label="附加要求"
      rows="2"
    /></label>
    <button
      class="primary"
      type="button"
      :disabled="busy || !markdown.trim()"
      @click="run"
    >
      {{ busy ? '正在提交…' : '运行测试' }}
    </button>
    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>

    <section
      v-if="job"
      class="result"
      aria-live="polite"
    >
      <h2>测试结果</h2>
      <p>{{ job.current_step }} · {{ job.progress }}%</p>
      <p
        v-if="job.error"
        class="err"
      >
        {{ job.error.message }}
      </p>
      <template v-if="job.status === 'completed'">
        <p><strong>校验结论：</strong>{{ result?.outcome === 'complete' ? '通过' : '部分通过，请检查警告' }}</p>
        <h3>标题</h3><p>{{ candidate?.title ?? '未建议' }}</p>
        <h3>摘要</h3><p>{{ candidate?.summary ?? '未建议' }}</p>
        <h3>正文预览</h3><pre>{{ candidate?.markdown ?? '未建议' }}</pre>
        <details v-if="validation">
          <summary>校验详情</summary><pre>{{ JSON.stringify(validation, null, 2) }}</pre>
        </details>
      </template>
    </section>
  </section>
</template>

<style scoped>
.skill-test { max-width: 820px; margin: 0 auto; padding: var(--space-4); }
header { display: flex; justify-content: space-between; gap: var(--space-3); align-items: start; }
h1 { margin: 0; font-size: 1.2rem; } header p { color: var(--color-text-muted); }
label { display: grid; gap: .35rem; margin: var(--space-3) 0; font-weight: 600; }
input, textarea { width: 100%; box-sizing: border-box; padding: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); font: inherit; }
.result { margin-top: var(--space-4); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 22rem; overflow: auto; background: var(--color-bg-subtle, #f6f7f9); padding: var(--space-2); }
.err { color: var(--status-danger, #dc2626); }
</style>
