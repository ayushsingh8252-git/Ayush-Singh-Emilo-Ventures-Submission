import { defineConfig, devices } from '@playwright/test'

// Uses the locally installed Google Chrome (channel: 'chrome'), so no browser download is needed.
// The suite starts its OWN backend (:8001, LLM disabled) and frontend (:5174) so results are
// deterministic and never call a paid LLM API, even if a dev server with LLM_ENABLED=true is running.
const API_PORT = 8001
const WEB_PORT = 5174

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    channel: 'chrome',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  ],
  webServer: [
    {
      // Quoted forward-slash path: works whether npm runs scripts through cmd.exe or a POSIX shell.
      command: process.platform === 'win32'
        ? `".venv/Scripts/python.exe" -m uvicorn app.main:app --port ${API_PORT}`
        : `.venv/bin/python -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: '../backend',
      url: `http://localhost:${API_PORT}/api/health`,
      env: { ...process.env, LLM_ENABLED: 'false', REC_CORS_ORIGINS: `http://localhost:${WEB_PORT}` },
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { ...process.env, VITE_API_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
