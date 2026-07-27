<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { planApi, type PlanTask, type QA } from '@/api/plan'

// Quick-add analysis review. The text is analyzed into scheduled task candidates;
// the user can answer up to a couple of clarifying questions and re-analyze, save
// the plan, or — at any point — just save the raw line as a plain todo.
const props = defineProps<{ text: string }>()
const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'save-raw', title: string): void
  (e: 'close'): void
}>()

const loading = ref(true)
const committing = ref(false)
const summary = ref('')
const tasks = ref<PlanTask[]>([])
const questions = ref<string[]>([])
const answers = ref<Record<string, string>>({})
const errored = ref(false)

async function analyze(withAnswers: QA[] = []): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const res = await planApi.analyze(props.text, withAnswers)
    if (res.error) {
      errored.value = true
    } else {
      summary.value = res.summary
      tasks.value = res.tasks
      questions.value = res.questions
    }
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}
onMounted(() => analyze())

function reanalyze(): void {
  const qa: QA[] = questions.value
    .map((q) => ({ question: q, answer: (answers.value[q] ?? '').trim() }))
    .filter((x) => x.answer)
  void analyze(qa)
}

async function savePlan(): Promise<void> {
  if (!tasks.value.length) return
  committing.value = true
  try {
    await planApi.commit(tasks.value)
    emit('saved')
  } catch {
    errored.value = true
  } finally {
    committing.value = false
  }
}

function saveRaw(): void {
  emit('save-raw', props.text)
}

// Compact date/time label for a candidate.
function whenLabel(t: PlanTask): string {
  if (!t.local_date) return '未排期'
  const time = t.local_time ? t.local_time.slice(0, 5) : ''
  const d = new Date(`${t.local_date}T00:00:00`)
  const today = new Date()
  const midnight = (x: Date) => {
    const y = new Date(x)
    y.setHours(0, 0, 0, 0)
    return y.getTime()
  }
  const days = Math.round((midnight(d) - midnight(today)) / 86400000)
  let day = `${d.getMonth() + 1}月${d.getDate()}日`
  if (days === 0) day = '今天'
  else if (days === 1) day = '明天'
  else if (days > 1 && days < 7) day = '周' + '日一二三四五六'[d.getDay()]
  return `${day} ${time}`.trim()
}
</script>

<template>
  <div
    class="plan-backdrop"
    @click.self="emit('close')"
  >
    <div
      class="plan"
      role="dialog"
      aria-label="分析待办"
    >
      <header>
        <strong>分析待办</strong>
        <button
          class="x"
          aria-label="关闭"
          @click="emit('close')"
        >✕</button>
      </header>
      <p class="src">“{{ text }}”</p>

      <div
        v-if="loading"
        class="analyzing"
      >
        <span class="spinner" />
        正在分析并安排…
      </div>

      <template v-else-if="errored">
        <p class="err">分析暂不可用。你可以直接存为一条待办。</p>
      </template>

      <template v-else>
        <p
          v-if="summary"
          class="summary"
        >{{ summary }}</p>

        <ul class="tasks">
          <li
            v-for="(t, i) in tasks"
            :key="i"
          >
            <span
              v-if="t.important"
              class="star"
              title="重要"
            >⭐</span>
            <span class="t-title">{{ t.title }}</span>
            <span
              class="chip"
              :class="{ none: !t.local_date }"
            >{{ whenLabel(t) }}</span>
          </li>
        </ul>

        <div
          v-if="questions.length"
          class="questions"
        >
          <p class="q-hint">回答后可让安排更准确（可跳过）：</p>
          <label
            v-for="(q, i) in questions"
            :key="i"
            class="q"
          >
            <span>{{ q }}</span>
            <input
              v-model="answers[q]"
              type="text"
              placeholder="可不填"
            >
          </label>
          <button
            class="ghost"
            :disabled="committing"
            @click="reanalyze"
          >回答并重新分析</button>
        </div>
      </template>

      <footer>
        <button
          class="ghost"
          :disabled="committing"
          @click="saveRaw"
        >直接存为待办</button>
        <button
          v-if="!loading && !errored && tasks.length"
          class="primary"
          :disabled="committing"
          @click="savePlan"
        >{{ committing ? '保存中…' : `保存 ${tasks.length} 项安排` }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.plan-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.4);
  display: grid;
  place-items: end center;
  padding: 0;
}
@media (min-width: 640px) {
  .plan-backdrop {
    place-items: center;
    padding: var(--space-4);
  }
}
.plan {
  width: min(520px, 100%);
  max-height: 88vh;
  overflow-y: auto;
  background: var(--color-surface);
  border-radius: 18px 18px 0 0;
  padding: var(--space-4);
  padding-bottom: calc(var(--safe-bottom, 0px) + var(--space-4));
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.28);
  animation: rise 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}
@media (min-width: 640px) {
  .plan {
    border-radius: 16px;
  }
}
@keyframes rise {
  from {
    transform: translateY(6%);
    opacity: 0;
  }
}
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.x {
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  min-width: 32px;
  min-height: 32px;
}
.src {
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}
.analyzing {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  padding: var(--space-4) 0;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border);
  border-top-color: var(--status-normal);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.summary {
  color: var(--status-ai);
  font-size: 0.9rem;
  margin: 0 0 var(--space-2);
}
.tasks {
  list-style: none;
  margin: 0 0 var(--space-3);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.tasks li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.t-title {
  flex: 1;
  font-weight: 600;
}
.chip {
  font-size: 0.78rem;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--status-normal) 16%, transparent);
  color: var(--status-normal);
  font-variant-numeric: tabular-nums;
}
.chip.none {
  background: var(--color-surface-2);
  color: var(--color-text-muted);
}
.questions {
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.q-hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}
.q {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}
.q input {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
.err {
  color: var(--status-urgent);
}
footer {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-3);
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 600;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
@media (prefers-reduced-motion: reduce) {
  .plan,
  .spinner {
    animation: none;
  }
}
</style>
