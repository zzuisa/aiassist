import { defineConfig, devices } from '@playwright/test'

// The operator-facing validation profile deliberately does not persist traces,
// videos, or browser screenshots. Authentication cookies and CSRF values must
// never enter a saved report; the test attaches its own desensitized dashboard.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'agent-api-validation.spec.ts',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report/agent-validation', open: 'never' }],
  ],
  outputDir: 'test-results/agent-validation',
  use: {
    baseURL: process.env.BASE_URL ?? 'https://llm.roguelife.de',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    { name: 'agent-api-validation', use: { ...devices['Desktop Chrome'] } },
  ],
})
