import type { VfsEntry } from '../api/client';
import type { AppDescriptor } from './types';
import React, { useSyncExternalStore } from 'react';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { PluginAppHost, PluginAppOpenHost } from './PluginHost';
import { getPluginAssetUrl } from '../plugins/urls';

let apps: AppDescriptor[] = [];
const listeners = new Set<() => void>();
export function subscribePluginApps(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function usePluginApps() {
  return useSyncExternalStore(subscribePluginApps, () => apps);
}

/**
 * 获取插件的唯一 key
 */
function getPluginAppKey(p: PluginItem): string {
  return `plugin:${p.key}`;
}

/**
 * 解析插件图标 URL
 * 支持绝对路径、相对路径（插件资源）、外部 URL
 */
function resolvePluginIcon(p: PluginItem): string | undefined {
  if (!p.icon) return undefined;

  // 外部 URL
  if (p.icon.startsWith('http://') || p.icon.startsWith('https://')) {
    return p.icon;
  }

  // 绝对路径
  if (p.icon.startsWith('/')) {
    return p.icon;
  }

  // 插件资源路径
  return getPluginAssetUrl(p.key, p.icon, p.content_hash);
}

function resolvePluginUseSystemWindow(p: PluginItem): boolean | undefined {
  const frontend = (p.manifest as any)?.frontend as any;
  const value = frontend?.use_system_window ?? frontend?.useSystemWindow;
  return typeof value === 'boolean' ? value : undefined;
}

function buildPluginApp(p: PluginItem): AppDescriptor {
  const key = getPluginAppKey(p);

  const supported = (entry: VfsEntry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    if (!p.supported_exts || p.supported_exts.length === 0) return true;
    return p.supported_exts.includes(ext);
  };

  return {
    key,
    name: p.name || `插件 ${p.key}`,
    supported,
    component: (props: any) => React.createElement(PluginAppHost, { plugin: p, ...props }),
    openAppComponent: p.open_app
      ? (props: any) => React.createElement(PluginAppOpenHost, { plugin: p, ...props })
      : undefined,
    iconUrl: resolvePluginIcon(p),
    default: false,
    defaultBounds: p.default_bounds || undefined,
    defaultMaximized: p.default_maximized || undefined,
    useSystemWindow: resolvePluginUseSystemWindow(p),
    description: p.description || undefined,
    author: p.author || undefined,
    supportedExts: p.supported_exts || undefined,
    website: p.website || undefined,
    github: p.github || undefined,
  };
}

async function loadApps() {
  try {
    const items = await pluginsApi.list();
    apps = items.filter(p => !p.status || p.status === 'active').map(buildPluginApp);
    listeners.forEach((listener) => listener());
  } catch {
    void 0;
  }
}

const appsLoadedPromise = loadApps();

export async function ensureAppsLoaded() {
  await appsLoadedPromise;
}

export function listPluginApps(): AppDescriptor[] {
  return apps;
}

export function getAppsForEntry(entry: VfsEntry): AppDescriptor[] {
  return apps.filter((a) => a.supported(entry));
}

export function getAppByKey(key: string): AppDescriptor | undefined {
  return apps.find((a) => a.key === key);
}

export function getDefaultAppForEntry(entry: VfsEntry): AppDescriptor | undefined {
  if (entry.is_dir) return;
  const ext = entry.name.split('.').pop()?.toLowerCase() || '';
  if (!ext) return apps.find((a) => a.supported(entry) && a.default);
  const saved = localStorage.getItem(`app.default.${ext}`);
  if (saved) {
    return apps.find((a) => a.key === saved && a.supported(entry)) || undefined;
  }
  return apps.find((a) => a.supported(entry) && a.default);
}

export type { AppDescriptor };
export type { AppComponentProps } from './types';

// Serialize refreshes so an older response cannot overwrite a newer installation.
let refresh = appsLoadedPromise;
export function reloadPluginApps() {
  refresh = refresh.then(loadApps);
  return refresh;
}
