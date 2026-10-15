/**
 * 插件外部依赖注入模块
 *
 * 宿主应用通过 window.__FOXEL_EXTERNALS__ 暴露共享依赖给插件使用
 * 插件开发时可以直接从 window.__FOXEL_EXTERNALS__ 获取 React、Antd 等依赖
 */

import * as React from 'react';
import * as ReactDOM from 'react-dom/client';
import * as antd from 'antd';
import * as AntdIcons from '@ant-design/icons';

// 宿主共享依赖（供插件复用）
import type MonacoEditor from '@monaco-editor/react';
import type Artplayer from 'artplayer';

// API 模块
import request, { vfsApi, API_BASE_URL } from '../api/client';
import { pluginsApi } from '../api/plugins';

// 类型定义
import type { VfsEntry, DirListing } from '../api/client';
import type { PluginItem } from '../api/plugins';
import { getActiveLang, normalizeLang, type Lang } from '../i18n/lang';
type Dict = Record<string, string>;
type Dicts = Partial<Record<Lang, Dict>>;

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
}

export type { FoxelHostApi, PluginContext, PluginAppContext, RegisteredPlugin } from './sdk/v1';
import type { RegisteredPlugin, PluginCapability } from './sdk/v1';
import { HOST_API_VERSION } from './sdk/v1';

/**
 * VFS API 包装
 */
const vfsApiWrapper = {
  list: vfsApi.list,
  stat: vfsApi.stat,
  mkdir: vfsApi.mkdir,
  rename: vfsApi.rename,
  deletePath: vfsApi.deletePath,
  copy: vfsApi.copy,
  move: vfsApi.move,
  streamUrl: vfsApi.streamUrl,
  getTempLinkToken: vfsApi.getTempLinkToken,
  getTempPublicUrl: vfsApi.getTempPublicUrl,
  readFile: vfsApi.readFile,
  uploadFile: vfsApi.uploadFile,
};

/**
 * 暴露给插件的外部依赖
 */
export interface FoxelExternals {
  // React 核心
  React: typeof React;
  ReactDOM: typeof ReactDOM;

  // UI 库
  antd: typeof antd;
  AntdIcons: typeof AntdIcons;

  // 编辑器/播放器
  MonacoEditor?: typeof MonacoEditor;
  Artplayer?: typeof Artplayer;
  loadCapability: (capability: PluginCapability) => Promise<void>;

  // i18n
  i18n?: {
    getLang: () => Lang;
    subscribe: (cb: (lang: Lang) => void) => () => void;
    create: (dicts: Dicts) => {
      t: (key: string, params?: Record<string, string | number>) => string;
      useI18n: () => { lang: Lang; t: (key: string, params?: Record<string, string | number>) => string };
    };
  };

  // Foxel API
  foxelApi: {
    /** HTTP 请求函数 */
    request: typeof request;
    /** VFS 文件系统 API */
    vfs: typeof vfsApiWrapper;
    /** 插件管理 API */
    plugins: typeof pluginsApi;
    /** API 基础 URL */
    baseUrl: string;
  };

  // 版本信息
  version: string;
}

// 声明全局类型
declare global {
  interface Window {
    __FOXEL_EXTERNALS__?: FoxelExternals;
    FoxelRegister?: (plugin: RegisteredPlugin) => void;
  }
}

/**
 * 初始化并暴露外部依赖
 */
export function initExternals(): void {
  const i18nApi = {
    getLang: () => getActiveLang(),
    subscribe: (cb: (lang: Lang) => void) => {
      const handler = (e: Event) => {
        const lang = (e as CustomEvent)?.detail?.lang as Lang;
        cb(normalizeLang(lang));
      };
      window.addEventListener('foxel:langchange', handler as any);
      return () => window.removeEventListener('foxel:langchange', handler as any);
    },
    create: (dicts: Dicts) => {
      const t = (key: string, params?: Record<string, string | number>) => {
        const lang = i18nApi.getLang();
        const dict = dicts[lang] || {};
        return interpolate(dict[key] ?? key, params);
      };

      const useI18n = () => {
        const [lang, setLang] = React.useState<Lang>(() => i18nApi.getLang());
        React.useEffect(() => i18nApi.subscribe(setLang), []);
        const tt = React.useCallback((key: string, params?: Record<string, string | number>) => {
          const dict = dicts[lang] || {};
          return interpolate(dict[key] ?? key, params);
        }, [lang]);
        return { lang, t: tt };
      };

      return { t, useI18n };
    },
  };

  if (window.__FOXEL_EXTERNALS__) {
    window.__FOXEL_EXTERNALS__.i18n = i18nApi;
    return; // 已初始化
  }

  window.__FOXEL_EXTERNALS__ = {
    // React 核心
    React,
    ReactDOM,

    // UI 库
    antd,
    AntdIcons,

    // 编辑器/播放器
    loadCapability,

    // i18n
    i18n: i18nApi,

    // Foxel API
    foxelApi: {
      request,
      vfs: vfsApiWrapper,
      plugins: pluginsApi,
      baseUrl: API_BASE_URL,
    },

    // 版本信息
    version: HOST_API_VERSION,
  };

  console.debug('[Foxel] Plugin externals initialized');
}

const capabilityLoads = new Map<PluginCapability, Promise<void>>();
export function loadCapability(capability: PluginCapability): Promise<void> {
  const pending = capabilityLoads.get(capability);
  if (pending) return pending;
  const load = (async () => {
    initExternals();
    const externals = window.__FOXEL_EXTERNALS__!;
    if (capability === 'monaco') externals.MonacoEditor = (await import('@monaco-editor/react')).default;
    else if (capability === 'artplayer') externals.Artplayer = (await import('artplayer')).default;
    else throw new Error(`Unsupported plugin capability: ${capability}`);
  })();
  capabilityLoads.set(capability, load);
  void load.catch(() => { capabilityLoads.delete(capability); });
  return load;
}

/**
 * 获取外部依赖
 */
export function getExternals(): FoxelExternals | undefined {
  return window.__FOXEL_EXTERNALS__;
}

// 导出类型供插件 SDK 使用
export type { VfsEntry, DirListing, PluginItem };
