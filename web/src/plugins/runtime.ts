/**
 * 插件运行时模块
 *
 * 负责：
 * 1. 加载和管理插件
 * 2. 处理插件注册
 */

import type { PluginItem } from '../api/plugins';
import type { RegisteredPlugin, PluginContext, PluginAppContext, FoxelHostApi } from './externals';

// 重新导出类型
export type { RegisteredPlugin, PluginContext, PluginAppContext, FoxelHostApi };

// 已加载的插件缓存
const loadedPlugins = new Map<string, RegisteredPlugin>();
// 等待加载的插件回调
const waiters = new Map<string, ((p: RegisteredPlugin) => void)[]>();
// 已注入的脚本 URL
const injected = new Set<string>();

/**
 * 全局插件注册函数
 * 插件加载后调用此函数注册自己
 */
window.FoxelRegister = (plugin: RegisteredPlugin) => {
  const pendingUrl = sessionStorage.getItem('foxel:pendingPluginUrl') || '';
  if (pendingUrl) {
    loadedPlugins.set(pendingUrl, plugin);
    const resolvers = waiters.get(pendingUrl) || [];
    resolvers.forEach((fn) => fn(plugin));
    waiters.delete(pendingUrl);
    sessionStorage.removeItem('foxel:pendingPluginUrl');
  } else {
    // 回退：使用第一个等待的 URL
    const anyUrl = Array.from(waiters.keys())[0];
    if (anyUrl) {
      loadedPlugins.set(anyUrl, plugin);
      const resolvers = waiters.get(anyUrl) || [];
      resolvers.forEach((fn) => fn(plugin));
      waiters.delete(anyUrl);
    }
  }
};

/**
 * 从 URL 加载插件
 */
export async function loadPluginFromUrl(url: string): Promise<RegisteredPlugin> {
  const existing = loadedPlugins.get(url);
  if (existing) return existing;

  return new Promise<RegisteredPlugin>((resolve, reject) => {
    const arr = waiters.get(url) || [];
    arr.push(resolve);
    waiters.set(url, arr);

    const ready = loadedPlugins.get(url);
    if (ready) {
      const resolvers = waiters.get(url) || [];
      resolvers.forEach((fn) => fn(ready));
      waiters.delete(url);
      return;
    }

    sessionStorage.setItem('foxel:pendingPluginUrl', url);

    if (!injected.has(url)) {
      injected.add(url);
      const script = document.createElement('script');
      script.src = url;
      script.async = true;
      script.onerror = () => {
        waiters.delete(url);
        reject(new Error('Failed to load plugin script: ' + url));
      };
      document.head.appendChild(script);
    }

    const t = setTimeout(() => {
      if (!loadedPlugins.get(url)) {
        waiters.delete(url);
        reject(new Error('Plugin did not call FoxelRegister: ' + url));
      }
    }, 15000);

    const last = arr[arr.length - 1];
    arr[arr.length - 1] = (p: RegisteredPlugin) => {
      clearTimeout(t);
      last(p);
    };
  });
}

/**
 * 获取插件 bundle URL
 */
export function getPluginBundleUrl(pluginKey: string): string {
  return `/api/plugins/${pluginKey}/bundle.js`;
}

/**
 * 获取插件资源 URL
 */
export function getPluginAssetUrl(pluginKey: string, assetPath: string): string {
  return `/api/plugins/${pluginKey}/assets/${assetPath}`;
}

/**
 * 加载插件
 */
export async function loadPlugin(plugin: Pick<PluginItem, 'key'>): Promise<RegisteredPlugin> {
  const bundleUrl = getPluginBundleUrl(plugin.key);
  return await loadPluginFromUrl(bundleUrl);
}

/**
 * 检查插件是否已加载
 */
export function isPluginLoaded(key: string): boolean {
  const bundleUrl = getPluginBundleUrl(key);
  return loadedPlugins.has(bundleUrl);
}

/**
 * 获取已加载的插件
 */
export function getLoadedPlugin(key: string): RegisteredPlugin | undefined {
  const bundleUrl = getPluginBundleUrl(key);
  return loadedPlugins.get(bundleUrl);
}

/**
 * 清除插件缓存（用于开发/调试）
 */
export function clearPluginCache(key?: string): void {
  if (key) {
    const bundleUrl = getPluginBundleUrl(key);
    loadedPlugins.delete(bundleUrl);
    injected.delete(bundleUrl);
  } else {
    loadedPlugins.clear();
    injected.clear();
  }
}
