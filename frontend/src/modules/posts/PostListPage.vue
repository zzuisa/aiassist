<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { postsApi, type Post } from '@/api/posts'

const router = useRouter()
const posts = ref<Post[]>([])

async function load(): Promise<void> {
  posts.value = await postsApi.list()
}

onMounted(load)

async function createNew(): Promise<void> {
  const post = await postsApi.create('未命名文章', '')
  await router.push(`/posts/${post.id}`)
}
</script>

<template>
  <main class="posts">
    <header class="head">
      <h1>博客</h1>
      <button
        type="button"
        @click="createNew"
      >
        新建文章
      </button>
    </header>
    <ul>
      <li
        v-for="p in posts"
        :key="p.id"
        @click="router.push(`/posts/${p.id}`)"
      >
        <span class="title">{{ p.title }}</span>
        <span
          class="status"
          :data-status="p.status"
        >
          {{ p.status === 'published' ? '已发布' : '草稿' }}
        </span>
      </li>
    </ul>
    <p
      v-if="posts.length === 0"
      class="muted"
    >
      还没有文章。
    </p>
  </main>
</template>

<style scoped>
.posts {
  padding: var(--space-4);
  max-width: 760px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.head button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
ul {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
}
li {
  display: flex;
  justify-content: space-between;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  cursor: pointer;
}
.status[data-status='published'] {
  color: var(--status-done);
}
.muted {
  color: var(--color-text-muted);
}
</style>
