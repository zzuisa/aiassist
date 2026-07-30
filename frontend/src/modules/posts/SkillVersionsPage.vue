<script setup lang="ts">
// Skill version timeline (spec 005, US5, T108).
//
// Versions are immutable: restoring appends a NEW current version rather than
// editing history. Pick two versions to compare their configs; restore any past
// version to make its config the new current version.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { blogSkillsApi, type SkillVersion } from '@/api/blogSkills'

const route = useRoute()
const skillId = computed(() => route.params.skillId as string)

const versions = ref<SkillVersion[]>([])
const leftId = ref<string | null>(null)
const rightId = ref<string | null>(null)
const busy = ref(false)
const error = ref('')

const left = computed(() => versions.value.find((v) => v.id === leftId.value) ?? null)
const right = computed(() => versions.value.find((v) => v.id === rightId.value) ?? null)

// Field-level equality across the two selected configs (for a compact compare).
const CONFIG_KEYS = [
  'processing_goal', 'applicable_content_classes', 'content_rules', 'title_rules',
  'summary_rules', 'body_structure', 'prohibitions', 'output_fields', 'field_policies',
  'max_content_chars', 'long_content_strategy',
] as const

const diffRows = computed(() => {
  if (!left.value?.config || !right.value?.config) return []
  const lc = left.value.config as Record<string, unknown>
  const rc = right.value.config as Record<string, unknown>
  return CONFIG_KEYS.map((k) => {
    const lv = JSON.stringify(lc[k])
    const rv = JSON.stringify(rc[k])
    return { key: k, left: lv, right: rv, changed: lv !== rv }
  })
})

async function load(): Promise<void> {
  versions.value = await blogSkillsApi.listVersions(skillId.value)
  if (versions.value.length >= 2) {
    rightId.value = versions.value[0].id
    leftId.value = versions.value[1].id
  } else if (versions.value.length === 1) {
    rightId.value = versions.value[0].id
  }
}

async function restore(versionId: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await blogSkillsApi.restoreVersion(skillId.value, versionId)
    await load()
  } catch {
    error.value = '恢复失败，请重试。'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="versions">
    <header class="head">
      <h1>技能版本</h1>
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

    <ul class="timeline">
      <li
        v-for="v in versions"
        :key="v.id"
        class="ver-row"
      >
        <label class="pick"><input
          type="radio"
          name="left"
          :checked="leftId === v.id"
          aria-label="对比左"
          @change="leftId = v.id"
        > 左</label>
        <label class="pick"><input
          type="radio"
          name="right"
          :checked="rightId === v.id"
          aria-label="对比右"
          @change="rightId = v.id"
        > 右</label>
        <span class="vnum">v{{ v.version_number }}</span>
        <span class="vsummary">{{ v.change_summary ?? '—' }}</span>
        <span class="vtime">{{ v.created_at }}</span>
        <button
          type="button"
          class="ghost small"
          :disabled="busy"
          @click="restore(v.id)"
        >
          恢复为新版本
        </button>
      </li>
    </ul>

    <section
      v-if="left && right && leftId !== rightId"
      class="compare"
    >
      <h2>v{{ left.version_number }} ↔ v{{ right.version_number }}</h2>
      <table>
        <thead>
          <tr><th>字段</th><th>v{{ left.version_number }}</th><th>v{{ right.version_number }}</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="row in diffRows"
            :key="row.key"
            :class="{ changed: row.changed }"
          >
            <td>{{ row.key }}</td>
            <td>{{ row.left }}</td>
            <td>{{ row.right }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<style scoped>
.versions {
  padding: var(--space-4);
  max-width: 900px;
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
.timeline {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0;
}
.ver-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.pick {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.vnum {
  font-weight: 600;
}
.vsummary {
  flex: 1;
  font-size: 0.85rem;
}
.vtime {
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.compare table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.compare th,
.compare td {
  text-align: left;
  padding: 0.35rem;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
  word-break: break-word;
}
.compare tr.changed {
  background: var(--status-warn-soft, #fef3c7);
}
.ghost.small {
  min-height: 2rem;
  font-size: 0.85rem;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: none;
  color: inherit;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
