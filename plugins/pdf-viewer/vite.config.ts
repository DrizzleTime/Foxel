import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/index.tsx'),
      formats: ['iife'],
      name: 'FoxelPdfViewer',
      fileName: () => 'index.js',
    },
    outDir: 'frontend',
    emptyOutDir: false,
    rollupOptions: {
      external: ['react', 'react-dom', 'react-dom/client', 'antd'],
      output: {
        globals: {
          'react': 'window.__FOXEL_EXTERNALS__.React',
          'react-dom': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'react-dom/client': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'antd': 'window.__FOXEL_EXTERNALS__.antd',
        },
        format: 'iife',
        extend: false,
      },
    },
    cssCodeSplit: false,
    minify: 'esbuild',
    sourcemap: false,
  },
});

