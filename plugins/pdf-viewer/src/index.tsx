/**
 * PDF 查看器插件入口
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import type { PluginContext } from './foxel-types';
import { PdfViewerApp } from './PdfViewerApp';

// 确保外部依赖已加载
const externals = window.__FOXEL_EXTERNALS__;
if (!externals) {
  console.error('[pdf-viewer] Foxel externals not found');
  throw new Error('Foxel externals not found');
}

// 注册插件
window.FoxelRegister({
  mount: (container: HTMLElement, ctx: PluginContext) => {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(PdfViewerApp, ctx));
    return () => root.unmount();
  },
});

