import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from '@/app/App.vue'
import { router } from '@/router'
import { setupPwa } from '@/pwa/register'
import '@/styles/tokens.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

// Register the static-only service worker (no-op in dev without a build).
if (import.meta.env.PROD) {
  setupPwa()
}
