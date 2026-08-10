<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { settingsApi, type MemoryItem } from '@/api/settings'

// AI memory: the answers you gave to the quick-add planner (e.g. 起床时间) are
// remembered here so future adds are smarter. You can edit or delete them.
const items = ref<MemoryItem[]>([])
const loading = ref(true)
const saving = ref(false)
const saved = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = (await settingsApi.getMemory()).items
  } finally {
    loading.value = false
  }
}
onMounted(load)

function remove(i: number): void {
  items.value.splice(i, 1)
}
async function save(): Promise<void> {
  saving.value = true
  saved.value = false
  try {
    items.value = (
      await settingsApi.putMemory(items.value.filter((x) => x.question.trim() && x.answer.trim()))
    ).items
    saved.value = true
    setTimeout(() => (saved.value = false), 2500)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="mem">
    <h2>🧠 AI 记忆</h2>
    <p class="hint">
      快速添加任务时你回答 AI 的问题（如作息、起床时间）会记在这里，之后的安排会自动参考。
    </p>

    <p
      v-if="loading"
      class="muted"
    >
      加载中…
    </p>
    <p
      v-else-if="!items.length"
      class="muted"
    >
      还没有记住的偏好。
    </p>

    <ul
      v-else
      class="list"
    >
      <li
        v-for="(it, i) in items"
        :key="i"
      >
        <div class="q">
          {{ it.question }}
        </div>
        <div class="row">
          <input
            v-model="it.answer"
            type="text"
            aria-label="记忆内容"
          >
          <button
            class="del"
            :aria-label="`删除：${it.question}`"
            @click="remove(i)"
          >
            ✕
          </button>
        </div>
      </li>
    </ul>

    <div
      v-if="items.length || saved"
      class="actions"
    >
      <span
        v-if="saved"
        class="ok"
      >已保存</span>
      <button
        class="primary"
        :disabled="saving"
        @click="save"
      >
        {{ saving ? '保存中…' : '保存记忆' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.mem {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.hint {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  margin: 0;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.q {
  font-size: 0.82rem;
  color: var(--color-text-muted);
  margin-bottom: 2px;
}
.row {
  display: flex;
  gap: var(--space-2);
}
.row input {
  flex: 1;
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
.del {
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--status-urgent);
  cursor: pointer;
}
.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}
.ok {
  color: var(--status-done);
  font-size: 0.85rem;
}
.primary {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: #fff;
  cursor: pointer;
}
.primary:disabled {
  opacity: 0.6;
}
</style>
