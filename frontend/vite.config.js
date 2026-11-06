import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  base: process.env.VITE_BASE_PATH||'/boards/equipment-agent/',
  plugins: [tailwindcss()],
  build: { outDir: 'dist', emptyOutDir: true, target: 'es2022' },
});
