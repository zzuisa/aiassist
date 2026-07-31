<script setup lang="ts">
// Category-first taxonomy surface (priority increment T184).
// The first slice intentionally keeps tags and keywords separate and focuses on
// a bounded primary category tree that can be reused by list and editor flows.
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { taxonomyApi, type TaxonomyItem } from '@/api/blogTaxonomy'

interface TreeItem extends TaxonomyItem {
  depth: number
}

const categories = ref<TaxonomyItem[]>([])
const name = ref('')
const description = ref('')
const parentId = ref('')
const busy = ref(false)
const error = ref('')
const saved = ref('')

function categoryOptionLabel(item: TreeItem): string {
  return `${'· '.repeat(item.depth)}${item.name}`
}

const treeItems = computed<TreeItem[]>(() => {
  const output: TreeItem[] = []
  const visited = new Set<string>()
  const children = (parent: string | null): TaxonomyItem[] =>
    categories.value
      .filter((item) => item.parent_id === parent)
      .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))

  function append(parent: string | null, depth: number): void {
    for (const item of children(parent)) {
      if (visited.has(item.id)) continue
      visited.add(item.id)
      output.push({ ...item, depth })
      append(item.id, Math.min(depth + 1, 3))
    }
  }

  append(null, 0)
  // Keep malformed/orphaned legacy rows visible rather than silently hiding them.
  for (const item of categories.value) {
    if (!visited.has(item.id)) output.push({ ...item, depth: 0 })
  }
  return output
})

async function load(): Promise<void> {
  try {
    categories.value = await taxonomyApi.list('category', true)
  } catch {
    error.value = '分类加载失败，请稍后重试。'
  }
}

async function createCategory(): Promise<void> {
  const trimmed = name.value.trim()
  if (!trimmed || busy.value) return
  busy.value = true
  error.value = ''
  saved.value = ''
  try {
    await taxonomyApi.create('category', {
      name: trimmed,
      description: description.value.trim() || null,
      parent_id: parentId.value || null,
    })
    name.value = ''
    description.value = ''
    parentId.value = ''
    saved.value = '分类已创建'
    await load()
  } catch {
    error.value = '分类创建失败，名称可能已存在或父级无效。'
  } finally {
    busy.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <main class="taxonomy">
    <header class="head">
      <div>
        <p class="eyebrow">
          博客结构化整理
        </p>
        <h1>分类</h1>
        <p class="intro">
          先用一个稳定的主分类说明文章属于哪个领域；标签和关键词分别承担横向浏览与检索职责。
        </p>
      </div>
      <RouterLink
        class="back"
        :to="{ name: 'blog' }"
      >
        返回文章
      </RouterLink>
    </header>

    <p
      v-if="error"
      class="message message--error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="saved"
      class="message message--saved"
      role="status"
    >
      {{ saved }}
    </p>

    <section class="layout">
      <section class="card category-card">
        <div class="card-head">
          <div>
            <h2>分类树</h2>
            <p>{{ categories.length }} 个启用分类 · 最多 3 层</p>
          </div>
          <span class="hint">文章可有一个主分类</span>
        </div>

        <ul
          v-if="treeItems.length"
          class="tree"
          aria-label="分类树"
        >
          <li
            v-for="item in treeItems"
            :key="item.id"
            class="tree-item"
            :style="{ paddingLeft: `${12 + item.depth * 20}px` }"
          >
            <span
              class="tree-mark"
              aria-hidden="true"
            >{{ item.depth ? '└' : '●' }}</span>
            <span class="tree-name">{{ item.name }}</span>
            <span class="tree-count">{{ item.usage_count }} 篇</span>
          </li>
        </ul>
        <p
          v-else
          class="empty"
        >
          还没有分类，先创建一个常用领域。
        </p>
      </section>

      <section class="card create-card">
        <h2>新建分类</h2>
        <p class="card-copy">
          建议使用稳定的领域名称，例如“技术复盘”“旅行”“项目记录”。
        </p>
        <label class="field">
          <span>名称</span>
          <input
            v-model="name"
            aria-label="分类名称"
            maxlength="120"
            placeholder="例如：技术复盘"
          >
        </label>
        <label class="field">
          <span>父分类（可选）</span>
          <select
            v-model="parentId"
            aria-label="父分类"
          >
            <option value="">顶层分类</option>
            <option
              v-for="item in treeItems"
              :key="item.id"
              :value="item.id"
            >
              {{ categoryOptionLabel(item) }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>说明（可选）</span>
          <textarea
            v-model="description"
            aria-label="分类说明"
            rows="3"
            maxlength="500"
            placeholder="这个分类用于归档什么内容？"
          />
        </label>
        <button
          type="button"
          class="primary"
          :disabled="busy || !name.trim()"
          @click="createCategory"
        >
          {{ busy ? '保存中…' : '创建分类' }}
        </button>
      </section>
    </section>
  </main>
</template>

<style scoped>
.taxonomy {
  max-width: 980px;
  margin: 0 auto;
  padding: var(--space-4);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
}
.eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--status-ai);
  font-size: 0.8rem;
  font-weight: 700;
}
h1,
h2 {
  margin: 0;
}
h1 {
  font-size: 1.35rem;
}
.intro,
.card-head p,
.card-copy {
  color: var(--color-text-muted);
  font-size: 0.88rem;
}
.intro {
  max-width: 650px;
  margin: var(--space-2) 0 0;
}
.back {
  color: var(--color-text-muted);
  white-space: nowrap;
}
.message {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
}
.message--error {
  color: var(--status-urgent);
  background: color-mix(in srgb, var(--status-urgent) 8%, var(--color-surface));
}
.message--saved {
  color: var(--status-done);
  background: color-mix(in srgb, var(--status-done) 8%, var(--color-surface));
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
  gap: var(--space-4);
  margin-top: var(--space-4);
}
.card {
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}
.card-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: baseline;
}
.card-head p {
  margin: var(--space-1) 0 0;
}
.hint {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  white-space: nowrap;
}
.tree {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
}
.tree-item {
  display: flex;
  align-items: center;
  min-height: var(--tap-target);
  gap: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}
.tree-item:last-child {
  border-bottom: 0;
}
.tree-mark {
  color: var(--status-ai);
  font-size: 0.75rem;
}
.tree-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tree-count {
  color: var(--color-text-muted);
  font-size: 0.78rem;
}
.empty {
  color: var(--color-text-muted);
}
.card h2 {
  font-size: 1rem;
}
.card-copy {
  margin: var(--space-2) 0 var(--space-4);
  line-height: 1.5;
}
.field {
  display: block;
  margin-bottom: var(--space-3);
}
.field > span {
  display: block;
  margin-bottom: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.field input,
.field select,
.field textarea {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
  background: var(--color-surface);
  color: inherit;
}
.primary {
  min-height: var(--tap-target);
  width: 100%;
  padding: 0 var(--space-3);
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (max-width: 680px) {
  .taxonomy {
    padding: var(--space-3);
  }
  .head {
    display: block;
  }
  .back {
    display: inline-block;
    margin-top: var(--space-2);
  }
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>
