import { defineConfig, devices } from '@playwright/test'

// Uses the locally installed Google Chrome (channel: 'chrome'), so no browser download is needed.
// Starts both servers if they are not already running.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'chrome',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  ],
  webServer: [
    {
      command: process.platform === 'win32'
        ? '.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000'
        : '.venv/bin/python -m uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: true,
      timeout: 180_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
