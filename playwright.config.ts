import { defineConfig } from '@playwright/test';

const pnpm = process.platform === 'win32' ? 'npx.cmd --yes pnpm@10.28.0' : 'pnpm';
const python = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : 'python';

export default defineConfig({
  testDir: './frontend/tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5183',
    channel: process.env.PLAYWRIGHT_CHANNEL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${pnpm} --filter @recruiter/candidate-h5 dev --port 5185 --host 127.0.0.1 --strictPort`,
      url: 'http://127.0.0.1:5185',
      timeout: 60_000,
      env: { VITE_USE_MOCK: 'false', API_PROXY_TARGET: 'http://127.0.0.1:8010' },
    },
    {
      command: `${python} scripts/e2e_server.py`,
      cwd: './backend',
      url: 'http://127.0.0.1:8010/health/ready',
      timeout: 60_000,
    },
    {
      command: `${pnpm} --filter @recruiter/hr-web dev --port 5183 --host 127.0.0.1 --strictPort`,
      url: 'http://127.0.0.1:5183',
      timeout: 60_000,
      env: { VITE_USE_MOCK: 'false', API_PROXY_TARGET: 'http://127.0.0.1:8010' },
    },
    {
      command: `${pnpm} --filter @recruiter/biz-h5 dev --port 5184 --host 127.0.0.1 --strictPort`,
      url: 'http://127.0.0.1:5184',
      timeout: 60_000,
      env: { VITE_USE_MOCK: 'false', API_PROXY_TARGET: 'http://127.0.0.1:8010' },
    },
  ],
});
