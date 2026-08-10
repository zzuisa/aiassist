<script setup lang="ts">
import type { CapabilityGap } from '@/api/agent'

defineProps<{
  gap: CapabilityGap
}>()

const sections: Array<{ key: keyof CapabilityGap; label: string }> = [
  { key: '缺失能力', label: '缺失能力' },
  { key: '缺失接口/字段/权限', label: '缺失接口、字段或权限' },
  { key: '可完成部分', label: '当前可完成' },
  { key: '不可完成部分', label: '当前不可完成' },
  { key: '建议补充项', label: '建议补充' },
]
</script>

<template>
  <section
    class="capability-gap"
    role="status"
    aria-label="能力缺口说明"
  >
    <header>
      <strong>当前能力不足，目标操作未执行</strong>
      <span>未使用模拟数据</span>
    </header>
    <dl>
      <div
        v-for="section in sections"
        :key="section.key"
      >
        <dt>{{ section.label }}</dt>
        <dd>
          <ul>
            <li
              v-for="item in gap[section.key]"
              :key="item"
            >
              {{ item }}
            </li>
          </ul>
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.capability-gap {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--status-due-soon);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}
header span,
dt {
  color: var(--color-text-muted);
}
dl,
dd,
ul {
  margin: 0;
}
dl {
  display: grid;
  gap: var(--space-2);
}
dl > div {
  display: grid;
  grid-template-columns: minmax(140px, 0.35fr) 1fr;
  gap: var(--space-2);
}
ul {
  padding-left: var(--space-4);
}
</style>
