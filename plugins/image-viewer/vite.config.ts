import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  define: {
    // 替换 process.env.NODE_ENV 引用
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/index.tsx'),
      formats: ['iife'],
      name: 'FoxelImageViewer',
      fileName: () => 'index.js',
    },
    outDir: 'frontend',
    emptyOutDir: false,
    rollupOptions: {
      // 排除宿主提供的依赖
      external: ['react', 'react-dom', 'react-dom/client', 'antd', '@ant-design/icons'],
      output: {
        // 映射全局变量
        globals: {
          'react': 'window.__FOXEL_EXTERNALS__.React',
          'react-dom': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'react-dom/client': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'antd': 'window.__FOXEL_EXTERNALS__.antd',
          '@ant-design/icons': 'window.__FOXEL_EXTERNALS__.AntdIcons',
        },
        // 使用 IIFE 格式，自执行
        format: 'iife',
        // 确保导出为自执行函数
        extend: false,
      },
    },
    // 关闭代码分割，打包成单个文件
    cssCodeSplit: false,
    // 生产环境优化
    minify: 'esbuild',
    sourcemap: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});

