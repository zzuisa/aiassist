import { onBeforeUnmount, onMounted, readonly, ref, type DeepReadonly, type Ref } from 'vue'

export const SHELL_COMPACT_MEDIA_QUERY = '(max-width: 1050px)'

export function useMediaQuery(query: string): DeepReadonly<Ref<boolean>> {
  const matches = ref(false)
  let mediaQuery: MediaQueryList | null = null

  function update(event?: MediaQueryListEvent): void {
    matches.value = event?.matches ?? mediaQuery?.matches ?? false
  }

  onMounted(() => {
    mediaQuery = window.matchMedia(query)
    update()
    mediaQuery.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    mediaQuery?.removeEventListener('change', update)
  })

  return readonly(matches)
}
