import { memo, useEffect, useMemo, useState } from 'react';
import { Button, Modal, Form, Input, Tag, message, Card, Typography, Popconfirm, Empty, Skeleton, theme, Divider, Tabs, Select, Pagination } from 'antd';
import { GithubOutlined, LinkOutlined } from '@ant-design/icons';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { loadPluginFromUrl, ensureManifest } from '../plugins/runtime';
import { reloadPluginApps, ensureAppsLoaded, listSystemApps, type AppDescriptor } from '../apps/registry';
import { useI18n } from '../i18n';
import { fetchRepoList, type RepoItem, buildCenterUrl } from '../api/pluginCenter';

const PluginsPage = memo(function PluginsPage() {
  const [data, setData] = useState<PluginItem[]>([]);
  const [systemApps, setSystemApps] = useState<AppDescriptor[]>([]);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'installed' | 'discover'>('installed');
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoQ, setRepoQ] = useState('');
  const [repoSort, setRepoSort] = useState<'createdAt' | 'downloads'>('createdAt');
  const [repoPage, setRepoPage] = useState(1);
  const [repoPageSize, setRepoPageSize] = useState(12);
  const [repoTotal, setRepoTotal] = useState(0);
  const [repoItems, setRepoItems] = useState<RepoItem[]>([]);
  const [installingKeys, setInstallingKeys] = useState<Record<string, boolean>>({});
  const [form] = Form.useForm<{ url: string }>();
  const { token } = theme.useToken();
  const { t } = useI18n();

  const reload = async () => {
    try { setLoading(true); setData(await pluginsApi.list()); } finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);
  useEffect(() => {
    (async () => {
      try {
        await ensureAppsLoaded();
        setSystemApps(listSystemApps());
      } catch {}
    })();
  }, []);

  const installedKeySet = useMemo(() => {
    const set = new Set<string>();
    data.forEach(p => { if (p.key) set.add(p.key); });
    return set;
  }, [data]);

  const reloadRepo = async () => {
    try {
      setRepoLoading(true);
      const res = await fetchRepoList({ query: repoQ || undefined, sort: repoSort, page: repoPage, pageSize: repoPageSize });
      setRepoItems(res.items || []);
      setRepoTotal(res.total || 0);
    } catch (e) {
      setRepoItems([]);
      setRepoTotal(0);
    } finally {
      setRepoLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'discover') reloadRepo();
  }, [tab, repoQ, repoSort, repoPage, repoPageSize]);

  const handleAdd = async () => {
    try {
      const { url } = await form.validateFields();
      const created = await pluginsApi.create({ url });
      try {
        const p = await loadPluginFromUrl(created.url);
        await ensureManifest(created.id, p);
      } catch {}
      setAdding(false);
      form.resetFields();
      await reload();
      await reloadPluginApps();
      message.success(t('Installed successfully'));
    } catch {}
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
          <a key="open" href={p.url} target="_blank" rel="noreferrer">{t('Open Link')}</a>,
          <Button key="copy" type="link" size="small" onClick={async () => { try { await navigator.clipboard.writeText(p.url); message.success(t('Link copied')); } catch {} }}>{t('Copy Link')}</Button>,
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
    const link = a.website || a.github || '';
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
            key="open"
            type="link"
            size="small"
            disabled={!link}
            onClick={() => { if (link) window.open(link, '_blank', 'noreferrer'); }}
          >
            {t('Open Link')}
          </Button>,
          <Button
            key="copy"
            type="link"
            size="small"
            disabled={!link}
            onClick={async () => {
              if (!link) return;
              try { await navigator.clipboard.writeText(link); message.success(t('Link copied')); } catch {}
            }}
          >
            {t('Copy Link')}
          </Button>,
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

  const renderRepoCard = (item: RepoItem) => {
    const icon = item.icon || '/plugins/demo-text-viewer.svg';
    const name = item.name || item.key;
    const exts = (item.supportedExts || []).slice(0, 6);
    const more = (item.supportedExts || []).length - exts.length;
    const installed = installedKeySet.has(item.key);
    const installing = !!installingKeys[item.key];
    const title = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <img src={icon} alt={name} style={{ width: 24, height: 24, objectFit: 'contain' }} onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/plugins/demo-text-viewer.svg'; }} />
        <span>{name}</span>
        {item.version && <Tag color="blue" style={{ marginLeft: 'auto' }}>{item.version}</Tag>}
      </div>
    );
    return (
      <Card
        key={item.key + '@' + (item.version || '')}
        title={title}
        hoverable
        size="small"
        styles={{ body: { padding: 12 } } as any}
        style={{ borderRadius: 10, boxShadow: token.boxShadowTertiary }}
        actions={[
          typeof item.downloads === 'number' ? (
            <span key="dl" style={{ color: token.colorTextTertiary, fontSize: 12 }}>
              {t('Downloads')}: {item.downloads}
            </span>
          ) : (
            <span key="dl-gap" />
          ),
          <Button
            key="install"
            type="link"
            size="small"
            disabled={installed || installing}
            loading={installing}
            onClick={async () => {
              try {
                setInstallingKeys(s => ({ ...s, [item.key]: true }));
                const url = buildCenterUrl(item.directUrl);
                const created = await pluginsApi.create({ url });
                try {
                  const p = await loadPluginFromUrl(created.url);
                  await ensureManifest(created.id, p);
                } catch {}
                await reload();
                await reloadPluginApps();
                message.success(t('Installed successfully'));
              } catch (e: any) {
                message.error(e?.message || 'Install failed');
              } finally {
                setInstallingKeys(s => ({ ...s, [item.key]: false }));
              }
            }}
          >
            {installed ? t('Installed already') : t('Install')}
          </Button>
        ]}
      >
        <Typography.Paragraph
          style={{ marginBottom: 8, minHeight: 44, lineHeight: '22px' }}
          ellipsis={{ rows: 2 }}
        >
          {item.description || '（暂无描述）'}
        </Typography.Paragraph>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', overflow: 'hidden', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
            {(exts.length > 0 ? exts : ['任意']).map(e => <Tag key={e} style={{ flex: 'none' }}>{e}</Tag>)}
          </div>
          {more > 0 && <Tag style={{ flex: 'none' }}>+{more}</Tag>}
        </div>
        <Divider style={{ margin: '8px 0' }} />
        {(item.author || item.github || item.website) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: token.colorTextTertiary, fontSize: 12 }}>
            {item.author && <span>{t('Author')}: {item.author}</span>}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              {item.github && (
                <a href={item.github || undefined} target="_blank" rel="noreferrer" title="GitHub">
                  <GithubOutlined style={{ fontSize: 16, color: token.colorTextTertiary }} />
                </a>
              )}
              {item.website && (
                <a href={item.website || undefined} target="_blank" rel="noreferrer" title={t('Website')}>
                  <LinkOutlined style={{ fontSize: 16, color: token.colorTextTertiary }} />
                </a>
              )}
            </span>
          </div>
        )}
      </Card>
    );
  };

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Button type="primary" onClick={() => setAdding(true)}>{t('Install App')}</Button>
        {tab === 'installed' && <Button onClick={reload} loading={loading}>{t('Refresh')}</Button>}
        <div style={{ marginLeft: 'auto' }} />
      </div>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as any)}
        items={[
          {
            key: 'installed',
            label: t('Installed'),
            children: (
              <>
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
              </>
            )
          },
          {
            key: 'discover',
            label: t('Discover'),
            children: (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                  <Input
                    placeholder={t('Search apps')}
                    value={repoQ}
                    onChange={e => { setRepoQ(e.target.value); setRepoPage(1); }}
                    allowClear
                    style={{ maxWidth: 360 }}
                    onPressEnter={() => { setRepoPage(1); reloadRepo(); }}
                  />
                  <Select
                    value={repoSort}
                    style={{ width: 200 }}
                    onChange={(v) => { setRepoSort(v); setRepoPage(1); }}
                    options={[
                      { value: 'createdAt', label: t('Created (newest)') },
                      { value: 'downloads', label: t('Downloads') },
                    ]}
                  />
                  <Button
                    icon={<LinkOutlined />}
                    href="https://center.foxel.cc"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Foxel Center
                  </Button>
                </div>
                {repoLoading ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Card key={i} style={{ borderRadius: 10 }}>
                        <Skeleton active avatar paragraph={{ rows: 3 }} />
                      </Card>
                    ))}
                  </div>
                ) : repoItems.length === 0 ? (
                  <Empty description={t('No results')} />
                ) : (
                  <>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
                      {repoItems.map(renderRepoCard)}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', marginTop: 12 }}>
                      <Pagination
                        current={repoPage}
                        pageSize={repoPageSize}
                        total={repoTotal}
                        showSizeChanger
                        pageSizeOptions={[12, 24, 48].map(String)}
                        onChange={(p, ps) => { setRepoPage(p); setRepoPageSize(ps); }}
                      />
                    </div>
                  </>
                )}
              </>
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
    </>
  );
});

export default PluginsPage;
