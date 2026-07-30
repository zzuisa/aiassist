<script setup lang="ts">
// Skill list (spec 005, US5, T106).
//
// Searchable list of the user's Skills with state + default-scope badges.
// Disabling a Skill that backs a default is guarded by a confirmation naming the
// impacted scopes, because it changes which Skill future optimizations resolve to.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { blogSkillsApi, type Skill } from '@/api/blogSkills'

const router = useRouter()
const skills = ref<Skill[]>([])
const query = ref('')
const busy = ref(false)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return skills.value
  return skills.value.filter(
    (s) => s.name.toLowerCase().includes(q) || (s.description ?? '').toLowerCase().includes(q),
  )
})

async function load(): Promise<void> {
  skills.value = await blogSkillsApi.list()
}

async function toggleEnabled(s: Skill): Promise<void> {
  if (busy.value) return
  if (s.enabled && s.default_scopes.length > 0) {
    const scopes = s.default_scopes.map((d) => `${d.scope_type}:${d.scope_key}`).join('、')
    if (!window.confirm(`该技能是以下范围的默认项：${scopes}。停用后这些范围将回退到全局默认。是否继续？`)) {
      return
    }
  }
  busy.value = true
  try {
    await blogSkillsApi.setEnabled(s.id, !s.enabled)
    await load()
  } finally {
    busy.value = false
  }
}

async function createNew(): Promise<void> {
  router.push({ name: 'blog-skill-new' })
}

async function copySkill(s: Skill): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const copy = await blogSkillsApi.copy(s.id)
    router.push({ name: 'blog-skill-edit', params: { skillId: copy.id } })
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="skills">
    <header class="head">
      <h1>AI 技能</h1>
      <button
        type="button"
        class="primary"
        @click="createNew"
      >
        新建技能
      </button>
    </header>

    <input
      v-model="query"
      class="search"
      type="search"
      placeholder="搜索技能…"
      aria-label="搜索技能"
    >

    <p
      v-if="filtered.length === 0"
      class="empty"
    >
      没有匹配的技能。
    </p>

    <ul class="skill-list">
      <li
        v-for="s in filtered"
        :key="s.id"
        class="skill-row"
      >
        <div class="skill-main">
          <RouterLink
            class="skill-name"
            :to="{ name: 'blog-skill-edit', params: { skillId: s.id } }"
          >
            {{ s.name }}
          </RouterLink>
          <div class="badges">
            <span
              class="badge"
              :data-on="s.enabled"
            >{{ s.enabled ? '启用' : '停用' }}</span>
            <span
              v-if="!s.current_version_complete"
              class="badge warn"
            >未完成</span>
            <span
              v-for="d in s.default_scopes"
              :key="d.scope_type + d.scope_key"
              class="badge default"
            >默认 {{ d.scope_type }}:{{ d.scope_key }}</span>
            <span
              v-if="s.current_version"
              class="ver"
            >v{{ s.current_version.version_number }}</span>
          </div>
        </div>
        <div class="skill-actions">
          <RouterLink
            class="ghost small"
            :to="{ name: 'blog-skill-versions', params: { skillId: s.id } }"
          >
            版本
          </RouterLink>
          <button
            type="button"
            class="ghost small"
            :disabled="busy"
            @click="copySkill(s)"
          >
            复制
          </button>
          <button
            type="button"
            class="ghost small"
            :disabled="busy"
            @click="toggleEnabled(s)"
          >
            {{ s.enabled ? '停用' : '启用' }}
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.skills {
  padding: var(--space-4);
  max-width: 820px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.head h1 {
  font-size: 1.2rem;
  margin: 0;
}
.search {
  width: 100%;
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.empty {
  color: var(--color-text-muted);
}
.skill-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.skill-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.skill-name {
  font-weight: 600;
  text-decoration: none;
  color: inherit;
}
.badges {
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
  margin-top: 0.35rem;
  align-items: center;
}
.badge {
  font-size: 0.72rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--color-surface-muted, #eee);
}
.badge[data-on='true'] {
  background: var(--status-done-soft, #dcfce7);
  color: var(--status-done, #16a34a);
}
.badge[data-on='false'] {
  background: var(--color-surface-muted, #eee);
  color: var(--color-text-muted);
}
.badge.warn {
  background: var(--status-warn-soft, #fef3c7);
}
.badge.default {
  background: var(--status-info-soft, #dbeafe);
  color: var(--status-info, #2563eb);
}
.ver {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.skill-actions {
  display: flex;
  gap: var(--space-2);
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.ghost.small {
  min-height: 2rem;
  font-size: 0.85rem;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: none;
  color: inherit;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
