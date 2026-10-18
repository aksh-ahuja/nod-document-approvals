import { defineConfig, devices } from '@playwright/test'

const apiPort = process.env.NOD_E2E_API_PORT || '8000'
const webPort = process.env.NOD_E2E_WEB_PORT || '5173'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.NOD_E2E_BASE_URL || `http://127.0.0.1:${webPort}`,
    trace: 'retain-on-failure',
    launchOptions: process.env.NOD_E2E_BROWSER_PATH ? { executablePath: process.env.NOD_E2E_BROWSER_PATH } : undefined,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: process.env.NOD_E2E_BASE_URL ? undefined : [
    {
      command: 'bash ../scripts/e2e-backend.sh',
      url: `http://127.0.0.1:${apiPort}/api/health/`,
      reuseExistingServer: false,
    },
    { command: `npm run dev -- --port ${webPort} --strictPort`, url: `http://127.0.0.1:${webPort}`, env: { NOD_DEV_API_URL: `http://127.0.0.1:${apiPort}` }, reuseExistingServer: false },
  ],
})
