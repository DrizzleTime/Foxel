import React, { useRef, useState } from 'react';
import type { AppComponentProps, AppOpenComponentProps } from '../types';
import { vfsApi } from '../../api/vfs';
import { loadPlugin, ensureManifest, type RegisteredPlugin } from '../../plugins/runtime';
import type { PluginItem } from '../../api/plugins';
import { useAsyncSafeEffect } from '../../hooks/useAsyncSafeEffect';
import { useI18n } from '../../i18n';

export interface PluginAppHostProps extends AppComponentProps {
  plugin: PluginItem;
}

export const PluginAppHost: React.FC<PluginAppHostProps> = ({ plugin, filePath, entry, onRequestClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;
  const { t } = useI18n();

  const pluginRef = useRef<RegisteredPlugin | null>(null);

  useAsyncSafeEffect(
    async ({ isDisposed }) => {
      try {
        const p = await loadPlugin(plugin);
        if (isDisposed()) return;
        pluginRef.current = p;
        await ensureManifest(plugin.id, p);
        if (isDisposed()) return;
        const token = await vfsApi.getTempLinkToken(filePath);
        if (isDisposed()) return;
        const downloadUrl = vfsApi.getTempPublicUrl(token.token);
        if (isDisposed() || !containerRef.current) return;
        await p.mount(containerRef.current, {
          filePath,
          entry,
          urls: { downloadUrl },
          host: { close: () => onCloseRef.current() },
        });
      } catch (e: any) {
        if (!isDisposed()) setError(e?.message || t('Plugin run failed'));
      }
    },
    [plugin.id, plugin.url, filePath],
    () => {
      try {
        if (pluginRef.current?.unmount && containerRef.current) {
          pluginRef.current.unmount(containerRef.current);
        }
      } catch { void 0; }
    },
  );

  if (error) {
    return <div style={{ padding: 12, color: 'red' }}>{t('Plugin Error')}: {error}</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%', overflow: 'auto' }} />;
};

export interface PluginAppOpenHostProps extends AppOpenComponentProps {
  plugin: PluginItem;
}

export const PluginAppOpenHost: React.FC<PluginAppOpenHostProps> = ({ plugin, onRequestClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const onCloseRef = useRef(onRequestClose);
  onCloseRef.current = onRequestClose;
  const { t } = useI18n();

  const pluginRef = useRef<RegisteredPlugin | null>(null);

  useAsyncSafeEffect(
    async ({ isDisposed }) => {
      try {
        const p = await loadPlugin(plugin);
        if (isDisposed()) return;
        pluginRef.current = p;
        await ensureManifest(plugin.id, p);
        if (isDisposed() || !containerRef.current) return;
        if (typeof p.mountApp !== 'function') {
          throw new Error('该插件不支持独立打开');
        }
        await p.mountApp(containerRef.current, {
          host: { close: () => onCloseRef.current() },
        });
      } catch (e: any) {
        if (!isDisposed()) setError(e?.message || t('Plugin run failed'));
      }
    },
    [plugin.id, plugin.url],
    () => {
      try {
        if (!containerRef.current) return;
        const p = pluginRef.current;
        if (p?.unmountApp) return p.unmountApp(containerRef.current);
        if (p?.unmount) return p.unmount(containerRef.current);
      } catch { void 0; }
    },
  );

  if (error) {
    return <div style={{ padding: 12, color: 'red' }}>{t('Plugin Error')}: {error}</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%', overflow: 'auto' }} />;
};
