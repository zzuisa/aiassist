<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { taxonomyApi, type TaxonomyCreate, type TaxonomyItem } from '@/api/blogTaxonomy'
import TaxonomyEditDrawer from './TaxonomyEditDrawer.vue'
import TaxonomyMergeDialog from './TaxonomyMergeDialog.vue'

interface TreeItem extends TaxonomyItem {
  depth: number
}

const kinds = ['category', 'tag', 'keyword'] as const
const labels = { category: '分类', tag: '标签', keyword: '关键词' }
const guidance = {
  category: '有限层级的内容领域，一篇文章只有一个主分类。',
  tag: '用于横向浏览的属性词，可设置别名、颜色并合并重复项。',
  keyword: '用于检索和统计，可设置同义词与停用词，并从正文重算。',
}
const activeKind = ref<TaxonomyItem['kind']>('category')
const allItems = ref<Record<TaxonomyItem['kind'], TaxonomyItem[]>>({ category: [], tag: [], keyword: [] })
const editing = ref<TaxonomyItem | null | undefined>(undefined)
const merging = ref<TaxonomyItem | null>(null)
const error = ref('')
const saved = ref('')
const categories = computed(() => allItems.value.category)
const currentItems = computed(() => allItems.value[activeKind.value])

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
    const [category, tag, keyword] = await Promise.all(kinds.map((kind) => taxonomyApi.list(kind)))
    allItems.value = { category, tag, keyword }
  } catch {
    error.value = '组织项加载失败，请稍后重试。'
  }
}

async function save(value: TaxonomyCreate): Promise<void> {
  error.value = ''
  saved.value = ''
  try {
    if (editing.value) await taxonomyApi.update(activeKind.value, editing.value.id, value)
    else await taxonomyApi.create(activeKind.value, value)
    saved.value = `${labels[activeKind.value]}已保存`
    editing.value = undefined
    await load()
  } catch {
    error.value = '保存失败，请检查名称/别名冲突、父级循环或层级深度。'
  }
}

async function recompute(): Promise<void> {
  error.value = ''
  try {
    const job = await taxonomyApi.recomputeKeywords()
    saved.value = `关键词重算已提交（${job.status}）`
  } catch {
    error.value = '关键词重算提交失败，请稍后重试。'
  }
}

function afterMerge(): void {
  merging.value = null
  void load()
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
        <h1>标签与分类</h1>
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

    <nav
      class="tabs"
      aria-label="组织类型"
    >
      <button
        v-for="kind in kinds"
        :key="kind"
        class="tab"
        :class="{ active: activeKind === kind }"
        @click="activeKind = kind"
      >
        {{ labels[kind] }}
      </button>
    </nav>
    <p class="intro concept">
      {{ guidance[activeKind] }}
    </p>

    <section class="card category-card">
      <div class="card-head">
        <div>
          <h2>{{ labels[activeKind] }}管理</h2>
          <p>{{ currentItems.length }} 项<span v-if="activeKind === 'category'"> · 最多 3 层</span></p>
        </div>
        <div class="actions">
          <button
            v-if="activeKind === 'keyword'"
            @click="recompute"
          >
            从正文重算
          </button><button
            class="primary compact"
            @click="editing = null"
          >
            新建{{ labels[activeKind] }}
          </button>
        </div>
      </div>

      <ul
        v-if="activeKind === 'category' && treeItems.length"
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
          <span
            v-if="!item.enabled"
            class="disabled"
          >已停用</span>
          <span class="tree-count">{{ item.usage_count }} 篇</span>
          <button
            class="link"
            @click="editing = item"
          >
            编辑
          </button><button
            class="link"
            @click="merging = item"
          >
            合并
          </button>
        </li>
      </ul>
      <table
        v-else-if="activeKind !== 'category' && currentItems.length"
        class="item-table"
      >
        <thead><tr><th>名称</th><th>别名/同义词</th><th>状态</th><th>使用</th><th>操作</th></tr></thead><tbody>
          <tr
            v-for="item in currentItems"
            :key="item.id"
          >
            <td>
              {{ item.name }}<i
                v-if="item.color"
                :style="{ background: item.color }"
              />
            </td><td>{{ item.aliases.join('、') || '—' }}</td><td>{{ item.enabled ? (item.stop_word ? '停用词' : '启用') : '已停用' }}</td><td>{{ item.usage_count }} 篇</td><td>
              <button
                class="link"
                @click="editing = item"
              >
                编辑
              </button><button
                class="link"
                @click="merging = item"
              >
                合并
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p
        v-else
        class="empty"
      >
        还没有{{ labels[activeKind] }}，可以先创建一个。
      </p>
    </section>
    <TaxonomyEditDrawer
      v-if="editing !== undefined"
      :item="editing"
      :kind="activeKind"
      :categories="categories"
      @close="editing = undefined"
      @save="save"
    />
    <TaxonomyMergeDialog
      v-if="merging"
      :kind="activeKind"
      :source="merging"
      :items="currentItems"
      @close="merging = null"
      @merged="afterMerge"
    />
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
.tabs {
  display: flex;
  gap: var(--space-1);
  margin-top: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}
.tab {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}
.tab.active {
  border-bottom-color: var(--status-ai);
  color: var(--color-text);
  font-weight: 700;
}
.concept {
  margin-bottom: var(--space-3);
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
.actions {
  display: flex;
  gap: var(--space-2);
}
.actions button,
.link {
  min-height: var(--tap-target);
  cursor: pointer;
}
.compact {
  width: auto;
}
.link {
  border: 0;
  background: transparent;
  color: var(--status-ai);
}
.disabled {
  padding: 0.1rem 0.35rem;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-text-muted) 12%, transparent);
  color: var(--color-text-muted);
  font-size: 0.72rem;
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
.item-table {
  width: 100%;
  margin-top: var(--space-3);
  border-collapse: collapse;
}
.item-table th,
.item-table td {
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  font-size: 0.85rem;
}
.item-table i {
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  margin-left: var(--space-1);
  border-radius: 50%;
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
  .card-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .item-table {
    display: block;
    overflow-x: auto;
  }
}
</style>
