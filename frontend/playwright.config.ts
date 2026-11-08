import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

/**
 * Browser smoke tests. The backend serves the built frontend on one origin (as in production):
 *   npm run build && npm run e2e
 * Locally set E2E_PYTHON to the backend venv python and PW_CHANNEL=chrome to use installed
 * Chrome; CI installs Playwright's Chromium and uses the system python.
 */
const PORT = 8123;
const backend = path.resolve(here, '..', 'backend');

export default defineConfig({
  testDir: 'e2e',
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0, // the hosted runners are slower and noisier than a laptop
  reporter: process.env.CI ? [['list'], ['github']] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices['Desktop Chrome'],
    viewport: { width: 1600, height: 1000 },
    channel: process.env.PW_CHANNEL || undefined,
    launchOptions: {
      args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
    },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `${process.env.E2E_PYTHON ?? 'python'} -m uvicorn trafficsim.server.app:app --port ${PORT} --workers 1`,
    cwd: backend,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      STATIC_DIR: path.resolve(here, 'dist'),
      MAX_SESSIONS: '4',
      COMPARE_WORKERS: '2',
      COMPARE_CACHE_DIR: path.resolve(backend, '.cache', 'e2e-compare'),
    },
  },
});
