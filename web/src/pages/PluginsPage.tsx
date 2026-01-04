import { memo, useEffect, useMemo, useState } from 'react';
import { Button, Tag, message, Card, Typography, Popconfirm, Empty, Skeleton, theme, Divider, Tabs, Upload } from 'antd';
import { GithubOutlined, LinkOutlined, UploadOutlined } from '@ant-design/icons';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { getAppByKey, reloadPluginApps } from '../apps/registry';
import { useI18n } from '../i18n';
import { useAppWindows } from '../contexts/AppWindowsContext';
import { getPluginAssetUrl } from '../plugins/runtime';
import type { UploadFile } from 'antd';

const PluginsPage = memo(function PluginsPage() {
  const [data, setData] = useState<PluginItem[]>([]);
  const [installing, setInstalling] = useState(false);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'installed' | 'discover'>('installed');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { openApp } = useAppWindows();

  const reload = async () => {
    try { setLoading(true); setData(await pluginsApi.list()); } finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);

  const handleInstall = async () => {
    if (fileList.length === 0) {
      message.warning(t('Please select a .foxpkg file'));
      return;
    }

    const file = fileList[0];
    if (!file.originFileObj) {
      message.error(t('Invalid file'));
      return;
    }

    try {
      setInstalling(true);
      const result = await pluginsApi.install(file.originFileObj);
      if (result.success) {
        message.success(result.message || t('Installed successfully'));
        setFileList([]);
        await reload();
        await reloadPluginApps();
      } else {
        message.error(result.message || t('Installation failed'));
        if (result.errors?.length) {
          result.errors.forEach(err => message.error(err));
        }
      }
    } catch (e: any) {
      message.error(e?.message || t('Installation failed'));
    } finally {
      setInstalling(false);
    }
  };

  /**
   * 解析插件图标 URL
   */
  const resolvePluginIcon = (p: PluginItem): string => {
    if (!p.icon) return '/logo.svg';
    if (p.icon.startsWith('http://') || p.icon.startsWith('https://') || p.icon.startsWith('/')) {
      return p.icon;
    }
    return getPluginAssetUrl(p.key, p.icon);
  };

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return data;
    return data.filter(p => (
      (p.name || '').toLowerCase().includes(s)
      || (p.author || '').toLowerCase().includes(s)
      || (p.key || '').toLowerCase().includes(s)
      || (p.description || '').toLowerCase().includes(s)
      || (p.supported_exts || []).some(e => e.toLowerCase().includes(s))
    ));
  }, [data, q]);

  const renderCard = (p: PluginItem) => {
    const icon = resolvePluginIcon(p);
    const name = p.name || `${t('Plugin')} ${p.key}`;
    const exts = (p.supported_exts || []).slice(0, 6);
    const more = (p.supported_exts || []).length - exts.length;
    const appKey = `plugin:${p.key}`;
    const app = getAppByKey(appKey);
    const canOpenApp = !!p.open_app;
    const title = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <img src={icon} alt={name} style={{ width: 24, height: 24, objectFit: 'contain' }} onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/logo.svg'; }} />
        <span>{name}</span>
        {p.version && <Tag color="blue" style={{ marginLeft: 'auto' }}>{p.version}</Tag>}
      </div>
    );
    return (
      <Card
        key={p.key}
        title={title}
        hoverable
        size="small"
        styles={{ body: { padding: 12 } } as any}
        style={{ borderRadius: 10, boxShadow: token.boxShadowTertiary }}
        actions={[
          <Button
            key="open-app"
            type="link"
            size="small"
            disabled={!canOpenApp}
            onClick={async () => {
              let target = app || getAppByKey(appKey);
              if (!target) {
                await reloadPluginApps();
                target = getAppByKey(appKey);
              }
              if (target?.openAppComponent) openApp(target);
            }}
          >
            {t('Open App')}
          </Button>,
          <Popconfirm key="del" title={t('Confirm delete this plugin?')} onConfirm={async () => { await pluginsApi.remove(p.key); await reload(); await reloadPluginApps(); }}>
            <Button type="link" danger size="small">{t('Uninstall')}</Button>
          </Popconfirm>
        ]}
      >
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Typography.Paragraph
              style={{ marginBottom: 8, minHeight: 44, lineHeight: '22px' }}
              ellipsis={{ rows: 2 }}
            >
              {p.description || t('No description')}
            </Typography.Paragraph>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', overflow: 'hidden', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
                {(exts.length > 0 ? exts : [t('Any')]).map(e => <Tag key={e} style={{ flex: 'none' }}>{e}</Tag>)}
              </div>
              {more > 0 && <Tag style={{ flex: 'none' }}>+{more}</Tag>}
            </div>
            <Divider style={{ margin: '8px 0' }} />
            {(p.author || p.github || p.website) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: token.colorTextTertiary, fontSize: 12 }}>
                {p.author && <span>{t('Author')}: {p.author}</span>}
                <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  {p.github && (
                    <a href={p.github || undefined} target="_blank" rel="noreferrer" title="GitHub">
                      <GithubOutlined style={{ fontSize: 16, color: token.colorTextTertiary }} />
                    </a>
                  )}
                  {p.website && (
                    <a href={p.website || undefined} target="_blank" rel="noreferrer" title={t('Website')}>
                      <LinkOutlined style={{ fontSize: 16, color: token.colorTextTertiary }} />
                    </a>
                  )}
                </span>
              </div>
            )}
          </div>
        </div>
      </Card>
    );
  };

  return (
    <div style={{ height: 'calc(100vh - 88px)', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Upload
          accept=".foxpkg"
          maxCount={1}
          fileList={fileList}
          onChange={({ fileList }) => setFileList(fileList)}
          beforeUpload={() => false}
          showUploadList={false}
        >
          <Button icon={<UploadOutlined />} type="primary">{t('Install Plugin')}</Button>
        </Upload>
        {fileList.length > 0 && (
          <>
            <span style={{ color: token.colorTextSecondary }}>{fileList[0].name}</span>
            <Button onClick={handleInstall} loading={installing} type="primary">{t('Confirm Install')}</Button>
            <Button onClick={() => setFileList([])}>{t('Cancel')}</Button>
          </>
        )}
        {tab === 'installed' && fileList.length === 0 && <Button onClick={reload} loading={loading}>{t('Refresh')}</Button>}
        <div style={{ marginLeft: 'auto' }} />
      </div>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as any)}
        className="plugins-tabs"
        items={[
          {
            key: 'installed',
            label: t('Installed'),
            children: (
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <input
                    type="text"
                    placeholder={t('Search name/author/extension')}
                    value={q}
                    onChange={e => setQ(e.target.value)}
                    style={{
                      maxWidth: 360,
                      padding: '4px 11px',
                      borderRadius: 6,
                      border: `1px solid ${token.colorBorder}`,
                      outline: 'none',
                      background: token.colorBgContainer,
                      color: token.colorText,
                    }}
                  />
                </div>
                <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 4 }}>
                  {loading ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                      {Array.from({ length: 6 }).map((_, i) => (
                        <Card key={i} style={{ borderRadius: 10 }}>
                          <Skeleton active avatar paragraph={{ rows: 3 }} />
                        </Card>
                      ))}
                    </div>
                  ) : filtered.length === 0 ? (
                    <Empty description={t('No plugins')} />
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
                      {filtered.map(renderCard)}
                    </div>
                  )}
                </div>
              </div>
            )
          },
          {
            key: 'discover',
            label: t('Discover'),
            children: (
              <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty description={`${t('Coming soon')} v2`} />
              </div>
            )
          }
        ]}
      />
    </div>
  );
});

export default PluginsPage;
