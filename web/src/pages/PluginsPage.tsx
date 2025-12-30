import { memo, useEffect, useMemo, useState } from 'react';
import { Button, Modal, Form, Input, Tag, message, Card, Typography, Popconfirm, Empty, Skeleton, theme, Divider, Tabs } from 'antd';
import { GithubOutlined, LinkOutlined } from '@ant-design/icons';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { loadPlugin, ensureManifest } from '../plugins/runtime';
import { getAppByKey, reloadPluginApps, ensureAppsLoaded, listSystemApps, type AppDescriptor } from '../apps/registry';
import { useI18n } from '../i18n';
import { useAppWindows } from '../contexts/AppWindowsContext';

const PluginsPage = memo(function PluginsPage() {
  const [data, setData] = useState<PluginItem[]>([]);
  const [systemApps, setSystemApps] = useState<AppDescriptor[]>([]);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'installed' | 'discover'>('installed');
  const [form] = Form.useForm<{ url: string }>();
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { openApp } = useAppWindows();

  const reload = async () => {
    try { setLoading(true); setData(await pluginsApi.list()); } finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);
  useEffect(() => {
    (async () => {
      try {
        await ensureAppsLoaded();
        setSystemApps(listSystemApps());
      } catch { void 0; }
    })();
  }, []);

  const handleAdd = async () => {
    try {
      const { url } = await form.validateFields();
      const created = await pluginsApi.create({ url });
      try {
        const p = await loadPlugin(created);
        await ensureManifest(created.id, p);
      } catch { void 0; }
      setAdding(false);
      form.resetFields();
      await reload();
      await reloadPluginApps();
      message.success(t('Installed successfully'));
    } catch { void 0; }
  };

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return data;
    return data.filter(p => (
      (p.name || '').toLowerCase().includes(s)
      || (p.author || '').toLowerCase().includes(s)
      || (p.url || '').toLowerCase().includes(s)
      || (p.description || '').toLowerCase().includes(s)
      || (p.supported_exts || []).some(e => e.toLowerCase().includes(s))
    ));
  }, [data, q]);

  const filteredSystemApps = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return systemApps;
    return systemApps.filter(a => (
      (a.name || '').toLowerCase().includes(s)
      || (a.author || '').toLowerCase().includes(s)
      || (a.website || '').toLowerCase().includes(s)
      || (a.github || '').toLowerCase().includes(s)
      || (a.description || '').toLowerCase().includes(s)
      || (a.supportedExts || []).some(e => e.toLowerCase().includes(s))
      || (a.key || '').toLowerCase().includes(s)
    ));
  }, [systemApps, q]);

  const renderCard = (p: PluginItem) => {
    const icon = p.icon || '/plugins/demo-text-viewer.svg';
    const name = p.name || `${t('Plugin')} ${p.id}`;
    const exts = (p.supported_exts || []).slice(0, 6);
    const more = (p.supported_exts || []).length - exts.length;
    const app = getAppByKey('plugin:' + p.id);
    const canOpenApp = !!p.open_app;
    const title = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <img src={icon} alt={name} style={{ width: 24, height: 24, objectFit: 'contain' }} onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/plugins/demo-text-viewer.svg'; }} />
        <span>{name}</span>
        {p.version && <Tag color="blue" style={{ marginLeft: 'auto' }}>{p.version}</Tag>}
      </div>
    );
    return (
      <Card
        key={p.id}
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
              let target = app || getAppByKey('plugin:' + p.id);
              if (!target) {
                await reloadPluginApps();
                target = getAppByKey('plugin:' + p.id);
              }
              if (target?.openAppComponent) openApp(target);
            }}
          >
            {t('Open App')}
          </Button>,
          <Button key="update-app" type="link" size="small" onClick={() => message.info(t('Coming soon'))}>{t('Update App')}</Button>,
          <Popconfirm key="del" title={t('Confirm delete this plugin?')} onConfirm={async () => { await pluginsApi.remove(p.id); await reload(); await reloadPluginApps(); }}>
            <Button type="link" danger size="small">{t('Delete')}</Button>
          </Popconfirm>
        ]}
      >
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Typography.Paragraph
              style={{ marginBottom: 8, minHeight: 44, lineHeight: '22px' }}
              ellipsis={{ rows: 2 }}
            >
              {p.description || '（暂无描述）'}
            </Typography.Paragraph>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', overflow: 'hidden', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
                {(exts.length > 0 ? exts : ['任意']).map(e => <Tag key={e} style={{ flex: 'none' }}>{e}</Tag>)}
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

  const renderSystemCard = (a: AppDescriptor) => {
    const icon = a.iconUrl || '/plugins/demo-text-viewer.svg';
    const name = a.name || a.key;
    const exts = (a.supportedExts || []).slice(0, 6);
    const more = (a.supportedExts || []).length - exts.length;
    const title = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <img src={icon} alt={name} style={{ width: 24, height: 24, objectFit: 'contain' }} onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/plugins/demo-text-viewer.svg'; }} />
        <span>{name}</span>
        <Tag style={{ marginLeft: 'auto' }}>{t('System App')}</Tag>
      </div>
    );
    return (
      <Card
        key={`system:${a.key}`}
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
            disabled={!a.openAppComponent}
            onClick={() => openApp(a)}
          >
            {t('Open App')}
          </Button>,
          <Button key="update-app" type="link" size="small" disabled onClick={() => message.info(t('Coming soon'))}>{t('Update App')}</Button>,
          <Button key="del" type="link" danger size="small" disabled>{t('Delete')}</Button>
        ]}
      >
        <Typography.Paragraph
          style={{ marginBottom: 8, minHeight: 44, lineHeight: '22px' }}
          ellipsis={{ rows: 2 }}
        >
          {a.description || '（暂无描述）'}
        </Typography.Paragraph>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', overflow: 'hidden', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
            {(exts.length > 0 ? exts : ['任意']).map(e => <Tag key={e} style={{ flex: 'none' }}>{e}</Tag>)}
          </div>
          {more > 0 && <Tag style={{ flex: 'none' }}>+{more}</Tag>}
        </div>
        <Divider style={{ margin: '8px 0' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: token.colorTextTertiary, fontSize: 12 }}>
          <span>{t('Author')}: {a.author || 'Foxel'}</span>
          <span style={{ marginLeft: 'auto', color: token.colorTextTertiary }}>{t('System App')}</span>
        </div>
      </Card>
    );
  };

  return (
    <div style={{ height: 'calc(100vh - 88px)', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Button type="primary" onClick={() => setAdding(true)}>{t('Install App')}</Button>
        {tab === 'installed' && <Button onClick={reload} loading={loading}>{t('Refresh')}</Button>}
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
                  <Input
                    placeholder={t('Search name/author/url/extension')}
                    value={q}
                    onChange={e => setQ(e.target.value)}
                    allowClear
                    style={{ maxWidth: 360 }}
                    onPressEnter={() => reload()}
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
                  ) : (filteredSystemApps.length + filtered.length) === 0 ? (
                    <Empty description={t('No plugins')} />
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
                      {filteredSystemApps.map(renderSystemCard)}
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

      <Modal
        title={t('Install App')}
        open={adding}
        onCancel={() => setAdding(false)}
        onOk={handleAdd}
        okText={t('Install')}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="url" label={t('App URL')} rules={[{ required: true }, { type: 'url', message: t('Please input a valid URL') }]}>
            <Input placeholder="https://example.com/plugin.js" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
});

export default PluginsPage;
