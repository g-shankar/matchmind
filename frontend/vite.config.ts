/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev and preview servers listen on this machine only. To open them from another
// device on your network (for example a phone), ask for it explicitly:
//   PITCHPULSE_DEV_HOST=0.0.0.0 npm run dev
// The dev tool chain has advisories that only matter when its server is reachable.
const host = process.env.PITCHPULSE_DEV_HOST?.trim() || 'localhost';

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, host },
  preview: { host },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
});
