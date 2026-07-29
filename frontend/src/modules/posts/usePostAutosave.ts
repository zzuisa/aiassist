// Post autosave composable (spec 005, US2, T060).
//
// Owns the save lifecycle for the editor: debounced autosave of a dirty buffer,
// explicit save, an in-flight guard, optimistic-version conflict handling with a
// reload path, and a visible save state the shell can render. It never loses the
// local buffer — a failed save keeps the pending changes so the user can retry.

import { onBeforeUnmount, readonly, ref, type Ref } from 'vue'
import { ApiError } from '@/api/client'
import { postsApi, type Post, type PostPatch } from '@/api/posts'

export type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'conflict' | 'error'

const AUTOSAVE_DELAY = 1200

export function usePostAutosave(post: Ref<Post | null>) {
  const state = ref<SaveState>('idle')
  const lastSavedAt = ref<number | null>(null)
  const errorMessage = ref('')
  // Fields changed since the last successful save.
  const pending = ref<PostPatch>({})
  let timer: ReturnType<typeof setTimeout> | null = null

  function isDirty(): boolean {
    return Object.keys(pending.value).length > 0
  }

  function clearTimer(): void {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  /** Stage a change and schedule a debounced autosave. */
  function update(patch: PostPatch): void {
    pending.value = { ...pending.value, ...patch }
    state.value = 'dirty'
    clearTimer()
    timer = setTimeout(() => void save(), AUTOSAVE_DELAY)
  }

  /** Persist pending changes now. Returns true on success. */
  async function save(): Promise<boolean> {
    clearTimer()
    if (!post.value || !isDirty() || state.value === 'saving') return false
    const target = post.value
    const patch = pending.value
    state.value = 'saving'
    errorMessage.value = ''
    try {
      const updated = await postsApi.patch(target.id, patch, target.version)
      post.value = updated
      // Only clear the fields we actually sent; a concurrent edit during the
      // request is preserved as still-pending.
      const stillPending: PostPatch = {}
      for (const key of Object.keys(pending.value) as Array<keyof PostPatch>) {
        if (!(key in patch)) stillPending[key] = pending.value[key] as never
      }
      pending.value = stillPending
      lastSavedAt.value = Date.now()
      state.value = isDirty() ? 'dirty' : 'saved'
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        state.value = 'conflict'
        errorMessage.value = '文章已在别处被修改。'
      } else {
        state.value = 'error'
        errorMessage.value = '保存失败，更改仍保留在本地。'
      }
      return false
    }
  }

  /** Discard local edits and reload the server copy (conflict resolution). */
  async function reload(): Promise<void> {
    if (!post.value) return
    const fresh = await postsApi.get(post.value.id)
    post.value = fresh
    pending.value = {}
    state.value = 'idle'
    errorMessage.value = ''
  }

  // Warn on tab close with unsaved changes.
  function beforeUnload(e: BeforeUnloadEvent): void {
    if (isDirty()) {
      e.preventDefault()
      e.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnload)
    clearTimer()
  })

  return {
    state: readonly(state),
    lastSavedAt: readonly(lastSavedAt),
    errorMessage: readonly(errorMessage),
    isDirty,
    update,
    save,
    reload,
  }
}
