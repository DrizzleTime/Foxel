import { memo, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Divider, Empty, List, Modal, Popconfirm, Progress, Skeleton, Space, Tabs, Tag, Typography, Upload, message, theme } from 'antd';
import { GithubOutlined, LinkOutlined, UploadOutlined } from '@ant-design/icons';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { getAppByKey, reloadPluginApps } from '../apps/registry';
import { useI18n } from '../i18n';
import { useAppWindows } from '../contexts/AppWindowsContext';
import { getPluginAssetUrl } from '../plugins/runtime';
import type { UploadFile } from 'antd';

type InstallStatus = 'pending' | 'installing' | 'success' | 'failed' | 'skipped';
type InstallState = Partial<{
  status: InstallStatus;
  message: string;
  errors: string[];
}>;

const PluginsPage = memo(function PluginsPage() {
  const [data, setData] = useState<PluginItem[]>([]);
  const [installing, setInstalling] = useState(false);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'installed' | 'discover'>('installed');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [installDone, setInstallDone] = useState(false);
  const [installStopReason, setInstallStopReason] = useState<string | undefined>(undefined);
  const [installFileState, setInstallFileState] = useState<Record<string, InstallState>>({});
  const { token } = theme.useToken();
  const { t, lang } = useI18n();
  const { openApp } = useAppWindows();

  const reload = async () => {
    try { setLoading(true); setData(await pluginsApi.list()); } finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);

  const resetInstallUi = () => {
    setInstallDone(false);
    setInstallStopReason(undefined);
    setInstallFileState({});
  };

  const closeInstallModal = () => {
    if (installing) return;
    setInstallModalOpen(false);
    setFileList([]);
    resetInstallUi();
  };

  const removeSelectedFile = (uid: string) => {
    if (installing || installDone) return;
    setFileList(prev => {
      const next = prev.filter(f => f.uid !== uid);
      if (next.length === 0) {
        setInstallModalOpen(false);
        resetInstallUi();
      }
      return next;
    });
    setInstallFileState(prev => {
      const next = { ...prev };
      delete next[uid];
      return next;
    });
  };

  const handleInstall = async () => {
    if (fileList.length === 0) {
      message.warning(t('Please select a .foxpkg file'));
      return;
    }

    const setState = (uid: string, patch: InstallState) => {
      setInstallFileState(prev => ({
        ...prev,
        [uid]: { ...(prev[uid] || {}), ...patch },
      }));
    };

    try {
      setInstalling(true);
      setInstallDone(false);
      setInstallStopReason(undefined);

      let stopReason: string | undefined;
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        const uid = file.uid;
        setState(uid, { status: 'installing' });

        if (!file.originFileObj) {
          stopReason = t('Invalid file');
          setState(uid, { status: 'failed', message: stopReason });
          for (let j = i + 1; j < fileList.length; j++) {
            setState(fileList[j].uid, { status: 'skipped' });
          }
          break;
        }

        try {
          const result = await pluginsApi.install(file.originFileObj);
          if (result.success) {
            setState(uid, {
              status: 'success',
              message: result.message || t('Installed successfully'),
              errors: result.errors,
            });
            continue;
          }

          stopReason = result.message || t('Installation failed');
          setState(uid, {
            status: 'failed',
            message: stopReason,
            errors: result.errors,
          });
          for (let j = i + 1; j < fileList.length; j++) {
            setState(fileList[j].uid, { status: 'skipped' });
          }
          break;
        } catch (e: any) {
          stopReason = e?.message || t('Installation failed');
          setState(uid, { status: 'failed', message: stopReason });
          for (let j = i + 1; j < fileList.length; j++) {
            setState(fileList[j].uid, { status: 'skipped' });
          }
          break;
        }
      }

      await reload();
      await reloadPluginApps();

      setInstallStopReason(stopReason);
      setInstallDone(true);
      if (stopReason) {
        message.error(stopReason);
      } else {
        message.success(t('Installed successfully'));
      }
    } catch (e: any) {
      const msg = e?.message || t('Installation failed');
      setInstallStopReason(msg);
      setInstallDone(true);
      message.error(msg);
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

  /**
   * 按当前语言解析插件文案（name/description）
   */
  const resolvePluginTexts = (p: PluginItem): { name?: string; description?: string } => {
    const i18n = (p.manifest as any)?.i18n as any;
    const entry = i18n?.[lang] as any;
    return {
      name: entry?.name || p.name || undefined,
      description: entry?.description || p.description || undefined,
    };
  };

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return data;
    return data.filter(p => (
      (resolvePluginTexts(p).name || '').toLowerCase().includes(s)
      || (p.author || '').toLowerCase().includes(s)
      || (p.key || '').toLowerCase().includes(s)
      || (resolvePluginTexts(p).description || '').toLowerCase().includes(s)
      || (p.supported_exts || []).some(e => e.toLowerCase().includes(s))
    ));
  }, [data, q, lang]);

  const renderCard = (p: PluginItem) => {
    const texts = resolvePluginTexts(p);
    const icon = resolvePluginIcon(p);
    const name = texts.name || `${t('Plugin')} ${p.key}`;
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
              {texts.description || t('No description')}
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
          multiple
          disabled={installing}
          fileList={fileList}
          onChange={({ fileList: newFileList }) => {
            setFileList(newFileList);
            if (newFileList.length > 0) {
              setInstallModalOpen(true);
              resetInstallUi();
            }
          }}
          beforeUpload={() => false}
          showUploadList={false}
        >
          <Button icon={<UploadOutlined />} type="primary">{t('Install Plugin')}</Button>
        </Upload>
        {tab === 'installed' && <Button onClick={reload} loading={loading} disabled={installing}>{t('Refresh')}</Button>}
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

      <Modal
        title={t('Confirm Install')}
        open={installModalOpen}
        onCancel={closeInstallModal}
        maskClosable={!installing}
        closable={!installing}
        width={640}
        footer={(() => {
          if (fileList.length === 0) {
            return <Button type="primary" onClick={closeInstallModal}>{t('Close')}</Button>;
          }
          if (installing) {
            return <Button type="primary" loading>{t('Installing')}</Button>;
          }
          if (installDone) {
            return <Button type="primary" onClick={closeInstallModal}>{t('Close')}</Button>;
          }
          return (
            <Space>
              <Button onClick={closeInstallModal}>{t('Cancel')}</Button>
              <Button type="primary" onClick={handleInstall}>{t('Confirm Install')}</Button>
            </Space>
          );
        })()}
      >
        {fileList.length === 0 ? (
          <Empty description={t('Please select a .foxpkg file')} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <Typography.Text>{t('Selected {count} files', { count: fileList.length })}</Typography.Text>
              <div style={{ marginTop: 4 }}>
                <Typography.Text type="secondary">{t('Installation will stop on first failure')}</Typography.Text>
              </div>
            </div>

            {installStopReason ? (
              <Alert type="error" showIcon message={installStopReason} />
            ) : null}

            <Progress
              percent={(() => {
                const finished = fileList.filter(f => {
                  const status = installFileState[f.uid]?.status;
                  return status === 'success' || status === 'failed';
                }).length;
                return fileList.length === 0 ? 0 : Math.round((finished / fileList.length) * 100);
              })()}
              status={installStopReason ? 'exception' : (installDone ? 'success' : (installing ? 'active' : 'normal'))}
              format={() => {
                const finished = fileList.filter(f => {
                  const status = installFileState[f.uid]?.status;
                  return status === 'success' || status === 'failed';
                }).length;
                return `${finished}/${fileList.length}`;
              }}
            />

            <List
              dataSource={fileList}
              bordered
              renderItem={(file) => {
                const st = (installFileState[file.uid]?.status || 'pending') as InstallStatus;
                const msg = installFileState[file.uid]?.message;
                const errors = installFileState[file.uid]?.errors || [];

                const statusText = (() => {
                  switch (st) {
                    case 'pending': return t('Pending');
                    case 'installing': return t('Installing');
                    case 'success': return t('Success');
                    case 'failed': return t('Failed');
                    case 'skipped': return t('Skipped');
                    default: return t('Pending');
                  }
                })();

                const statusColor = (() => {
                  switch (st) {
                    case 'installing': return 'blue';
                    case 'success': return 'green';
                    case 'failed': return 'red';
                    case 'skipped': return 'orange';
                    default: return 'default';
                  }
                })();

                return (
                  <List.Item
                    actions={[
                      (!installing && !installDone) ? (
                        <Button key="remove" type="link" danger onClick={() => removeSelectedFile(file.uid)}>
                          {t('Remove')}
                        </Button>
                      ) : null,
                      <Tag key="status" color={statusColor}>{statusText}</Tag>,
                    ].filter(Boolean) as any}
                  >
                    <List.Item.Meta
                      title={file.name}
                      description={
                        (msg || errors.length > 0) ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {msg ? (
                              <Typography.Text type={st === 'failed' ? 'danger' : (st === 'success' ? 'success' : 'secondary')}>
                                {msg}
                              </Typography.Text>
                            ) : null}
                            {errors.length > 0 ? (
                              <Typography.Text type={st === 'failed' ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>
                                {errors.join('; ')}
                              </Typography.Text>
                            ) : null}
                          </div>
                        ) : null
                      }
                    />
                  </List.Item>
                );
              }}
            />
          </div>
        )}
      </Modal>
    </div>
  );
});

export default PluginsPage;
