import React, { useRef, useState, useCallback } from 'react';
import { message } from 'antd';
import type { AppComponentProps, AppOpenComponentProps } from '../types';
import { vfsApi } from '../../api/vfs';
import {
  loadPlugin,
  type RegisteredPlugin,
  type FoxelHostApi,
} from '../../plugins/runtime';
import type { PluginItem } from '../../api/plugins';
import { useAsyncSafeEffect } from '../../hooks/useAsyncSafeEffect';
import { useI18n } from '../../i18n';
import request from '../../api/client';

export interface PluginAppHostProps extends AppComponentProps {
  plugin: PluginItem;
}

/**
 * 创建宿主 API
 */
function createHostApi(onClose: () => void): FoxelHostApi {
  return {
    close: onClose,

    showMessage: (type, content) => {
      switch (type) {
        case 'success':
          message.success(content);
          break;
        case 'error':
          message.error(content);
          break;
        case 'warning':
          message.warning(content);
          break;
        case 'info':
        default:
          message.info(content);
          break;
      }
    },

    callApi: async <T = unknown>(path: string, options?: RequestInit & { json?: unknown }) => {
      return request<T>(path, options);
    },

    getTempLink: async (filePath: string) => {
      const token = await vfsApi.getTempLinkToken(filePath);
      return vfsApi.getTempPublicUrl(token.token);
    },

    getStreamUrl: (filePath: string) => {
      const safePath = filePath.replace(/^\/+/, '');
      return vfsApi.streamUrl(safePath);
    },
  };
}

/**
 * 插件宿主组件 - 文件打开模式
 */
export const PluginAppHost: React.FC<PluginAppHostProps> = ({
  plugin,
  filePath,
  entry,
  onRequestClose,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;
  const { t } = useI18n();

  const pluginRef = useRef<RegisteredPlugin | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  const handleClose = useCallback(() => {
    onCloseRef.current();
  }, []);

  useAsyncSafeEffect(
    async ({ isDisposed }) => {
      try {
        const p = await loadPlugin(plugin);
        if (isDisposed()) return;
        pluginRef.current = p;

        const token = await vfsApi.getTempLinkToken(filePath);
        if (isDisposed()) return;

        const downloadUrl = vfsApi.getTempPublicUrl(token.token);
        const streamUrl = vfsApi.streamUrl(filePath.replace(/^\/+/, ''));

        if (isDisposed() || !containerRef.current) return;

        const hostApi = createHostApi(handleClose);

        const result = await p.mount(containerRef.current, {
          filePath,
          entry,
          urls: { downloadUrl, streamUrl },
          host: hostApi,
        });

        // 保存清理函数
        if (typeof result === 'function') {
          cleanupRef.current = result;
        }
      } catch (e: unknown) {
        if (!isDisposed()) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(msg || t('Plugin run failed'));
        }
      }
    },
    [plugin.key, filePath, handleClose],
    () => {
      try {
        // 优先使用 mount 返回的清理函数
        if (cleanupRef.current) {
          cleanupRef.current();
          cleanupRef.current = null;
        } else if (pluginRef.current?.unmount && containerRef.current) {
          pluginRef.current.unmount(containerRef.current);
        }
      } catch {
        void 0;
      }
    }
  );

  if (error) {
    return (
      <div style={{ padding: 12, color: 'red' }}>
        {t('Plugin Error')}: {error}
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', overflow: 'auto' }} />
  );
};

export interface PluginAppOpenHostProps extends AppOpenComponentProps {
  plugin: PluginItem;
}

/**
 * 插件宿主组件 - 独立应用模式
 */
export const PluginAppOpenHost: React.FC<PluginAppOpenHostProps> = ({
  plugin,
  onRequestClose,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;
  const { t } = useI18n();

  const pluginRef = useRef<RegisteredPlugin | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  const handleClose = useCallback(() => {
    onCloseRef.current();
  }, []);

  useAsyncSafeEffect(
    async ({ isDisposed }) => {
      try {
        const p = await loadPlugin(plugin);
        if (isDisposed()) return;
        pluginRef.current = p;

        if (isDisposed() || !containerRef.current) return;

        if (typeof p.mountApp !== 'function') {
          throw new Error(t('This plugin does not support standalone mode'));
        }

        const hostApi = createHostApi(handleClose);

        const result = await p.mountApp(containerRef.current, {
          host: hostApi,
        });

        // 保存清理函数
        if (typeof result === 'function') {
          cleanupRef.current = result;
        }
      } catch (e: unknown) {
        if (!isDisposed()) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(msg || t('Plugin run failed'));
        }
      }
    },
    [plugin.key, handleClose],
    () => {
      try {
        // 优先使用 mountApp 返回的清理函数
        if (cleanupRef.current) {
          cleanupRef.current();
          cleanupRef.current = null;
        } else if (containerRef.current) {
          const p = pluginRef.current;
          if (p?.unmountApp) {
            p.unmountApp(containerRef.current);
          } else if (p?.unmount) {
            p.unmount(containerRef.current);
          }
        }
      } catch {
        void 0;
      }
    }
  );

  if (error) {
    return (
      <div style={{ padding: 12, color: 'red' }}>
        {t('Plugin Error')}: {error}
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', overflow: 'auto' }} />
  );
};
