// Static-only service worker registration with a safe update prompt.
// The SW precaches versioned static assets only (API/SSE/auth are NetworkOnly),
// and updates are applied on explicit user confirmation — never auto-reloading
// so unsaved task/blog input is not lost.
import { registerSW } from 'virtual:pwa-register'

export function setupPwa(): void {
  const updateSW = registerSW({
    immediate: false,
    onNeedRefresh() {
      // Non-blocking prompt; the user chooses when to reload.
      if (window.confirm('有新版本可用，是否刷新以更新？')) {
        void updateSW(true)
      }
    },
    onOfflineReady() {
      // Offline shell is cached; private data still requires the network.
    },
  })
}
