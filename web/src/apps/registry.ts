import type { VfsEntry } from '../api/client';
import type { AppDescriptor } from './types';
import React from 'react';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { PluginAppHost, PluginAppOpenHost } from './PluginHost';
import { getPluginAssetUrl } from '../plugins/runtime';

const apps: AppDescriptor[] = [];

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
  return getPluginAssetUrl(p.key, p.icon);
}

function registerPluginAsApp(p: PluginItem) {
  const key = getPluginAppKey(p);
  if (apps.find((a) => a.key === key)) return;

  const supported = (entry: VfsEntry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    if (!p.supported_exts || p.supported_exts.length === 0) return true;
    return p.supported_exts.includes(ext);
  };

  apps.push({
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
    description: p.description || undefined,
    author: p.author || undefined,
    supportedExts: p.supported_exts || undefined,
    website: p.website || undefined,
    github: p.github || undefined,
  });
}

async function loadApps() {
  try {
    const items = await pluginsApi.list();
    items.forEach((p) => registerPluginAsApp(p));
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

export async function reloadPluginApps() {
  try {
    const items = await pluginsApi.list();

    // 生成要保留的 key 集合
    const keepKeys = new Set(items.map((p) => getPluginAppKey(p)));

    // 移除已卸载的插件应用
    for (let i = apps.length - 1; i >= 0; i--) {
      const a = apps[i];
      if (!keepKeys.has(a.key)) {
        apps.splice(i, 1);
      }
    }

    // 更新或添加插件应用
    items.forEach((p) => {
      const key = getPluginAppKey(p);
      const existing = apps.find((a) => a.key === key);
      if (!existing) {
        registerPluginAsApp(p);
      } else {
        // 更新现有应用信息
        existing.name = p.name || `插件 ${p.key}`;
        existing.defaultBounds = p.default_bounds || undefined;
        existing.defaultMaximized = p.default_maximized || undefined;
        existing.iconUrl = resolvePluginIcon(p);
        existing.description = p.description || undefined;
        existing.author = p.author || undefined;
        existing.supportedExts = p.supported_exts || undefined;
        existing.openAppComponent = p.open_app
          ? (props: any) => React.createElement(PluginAppOpenHost, { plugin: p, ...props })
          : undefined;
      }
    });
  } catch {
    void 0;
  }
}
