/**
 * 视频库插件入口
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import type { PluginContext, AppContext } from './foxel-types';
import { VideoPlayerApp } from './VideoPlayerApp';
import { VideoLibraryApp } from './VideoLibraryApp';

// 确保外部依赖已加载
const externals = window.__FOXEL_EXTERNALS__;
if (!externals) {
  console.error('[video-library] Foxel externals not found');
  throw new Error('Foxel externals not found');
}

// 注册插件
window.FoxelRegister({
  // 文件打开模式
  mount: (container: HTMLElement, ctx: PluginContext) => {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(VideoPlayerApp, ctx));
    return () => root.unmount();
  },

  // 独立应用模式
  mountApp: (container: HTMLElement, ctx: AppContext) => {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(VideoLibraryApp, ctx));
    return () => root.unmount();
  },
});

