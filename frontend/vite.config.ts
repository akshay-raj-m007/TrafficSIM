/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev, the FastAPI backend runs on :8000; proxy API + WebSocket so the
// browser sees a single origin, exactly like the production Docker image.
const BACKEND = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1000,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
