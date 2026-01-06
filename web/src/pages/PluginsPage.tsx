import { memo, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert, Button, Card, Collapse, Empty, List, Modal, Popconfirm, Progress, Skeleton, Space, Tabs, Tag, Typography, Upload, message, theme } from 'antd';
import { GithubOutlined, LinkOutlined, UploadOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { pluginsApi, type PluginItem } from '../api/plugins';
import { getAppByKey, reloadPluginApps } from '../apps/registry';
import { useI18n } from '../i18n';
import { useAppWindows } from '../contexts/AppWindowsContext';
import { getPluginAssetUrl } from '../plugins/runtime';
import { fetchFoxelCoreAppDetail, fetchFoxelCoreApps, downloadFoxelCoreApp, type FoxelCoreApp, type FoxelCoreAppDetail } from '../api/pluginCenter';
import type { UploadFile } from 'antd';
import ReactMarkdown from 'react-markdown';

type InstallStatus = 'pending' | 'installing' | 'success' | 'failed' | 'skipped';
type InstallState = Partial<{
  status: InstallStatus;
  message: string;
  errors: string[];
}>;

type CenterCardProps = {
  iconUrl: string;
  iconAlt: string;
  name: ReactNode;
  version?: ReactNode;
  description?: ReactNode;
  metaLeft?: ReactNode;
  metaRight?: ReactNode;
  pills?: string[];
  footerLeft?: ReactNode;
  footerRight?: ReactNode;
  onIconClick?: () => void;
  onTitleClick?: () => void;
};

function buildCardPills(items: Array<string | null | undefined> | null | undefined, fallback?: string) {
  const cleaned = (items || []).map(v => (v || '').trim()).filter(Boolean);
  if (cleaned.length === 0) return fallback ? [fallback] : [];
  if (cleaned.length <= 2) return cleaned;
  return [cleaned[0], `+${cleaned.length - 1}`];
}

const CenterCard = memo(function CenterCard(props: CenterCardProps) {
  const {
    iconUrl,
    iconAlt,
    name,
    version,
    description,
    metaLeft,
    metaRight,
    pills,
    footerLeft,
    footerRight,
    onIconClick,
    onTitleClick,
  } = props;

  return (
    <div className="fx-center-card">
      <div className="fx-center-card-hero">
        <div
          className="fx-center-card-iconbox"
          style={onIconClick ? { cursor: 'pointer' } : undefined}
          role={onIconClick ? 'button' : undefined}
          tabIndex={onIconClick ? 0 : undefined}
          onClick={onIconClick}
          onKeyDown={onIconClick ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onIconClick();
            }
          } : undefined}
        >
          <img
            className="fx-center-card-icon"
            src={iconUrl}
            alt={iconAlt}
            loading="lazy"
            onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/logo.svg'; }}
          />
        </div>
        {pills && pills.length > 0 ? (
          <div className="fx-center-card-pills">
            {pills.slice(0, 2).map(pill => (
              <span key={pill} className="fx-center-pill">
                {pill}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="fx-center-card-body">
        <div className="fx-center-card-titleRow">
          <div
            className="fx-center-card-title"
            title={typeof name === 'string' ? name : undefined}
            style={onTitleClick ? { cursor: 'pointer' } : undefined}
            role={onTitleClick ? 'button' : undefined}
            tabIndex={onTitleClick ? 0 : undefined}
            onClick={onTitleClick}
            onKeyDown={onTitleClick ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onTitleClick();
              }
            } : undefined}
          >
            {name}
          </div>
          {version ? <div className="fx-center-card-version">{version}</div> : null}
        </div>

        {metaLeft || metaRight ? (
          <div className="fx-center-card-metaRow">
            <span className="fx-center-card-metaLeft">{metaLeft}</span>
            <span className="fx-center-card-metaRight">{metaRight}</span>
          </div>
        ) : null}

        {description ? <div className="fx-center-card-desc">{description}</div> : null}
      </div>

      {footerLeft || footerRight ? (
        <div className="fx-center-card-footer">
          <div className="fx-center-card-footerLeft">{footerLeft}</div>
          <div className="fx-center-card-footerRight">{footerRight}</div>
        </div>
      ) : null}
    </div>
  );
});

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
  
  // 应用发现相关状态
  const [discoveryApps, setDiscoveryApps] = useState<FoxelCoreApp[]>([]);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | undefined>(undefined);
  const [discoverySearch, setDiscoverySearch] = useState('');
  const [downloadingApps, setDownloadingApps] = useState<Set<string>>(new Set());

  // 应用详情弹窗状态
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailKey, setDetailKey] = useState<string | null>(null);
  const [detailSummary, setDetailSummary] = useState<FoxelCoreApp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | undefined>(undefined);
  const [detailApp, setDetailApp] = useState<FoxelCoreAppDetail | null>(null);
  const [detailReloadId, setDetailReloadId] = useState(0);
  
  const { token } = theme.useToken();
  const { t, lang } = useI18n();
  const { openApp } = useAppWindows();

  const reload = useCallback(async () => {
    try { setLoading(true); setData(await pluginsApi.list()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  // 加载应用发现列表
  const loadDiscoveryApps = useCallback(async () => {
    try {
      setDiscoveryLoading(true);
      setDiscoveryError(undefined);
      const apps = await fetchFoxelCoreApps();
      setDiscoveryApps(apps);
    } catch (e: any) {
      setDiscoveryError(e?.message || t('Failed to load apps'));
    } finally {
      setDiscoveryLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (tab === 'discover' && discoveryApps.length === 0 && !discoveryError) {
      void loadDiscoveryApps();
    }
  }, [discoveryApps.length, discoveryError, loadDiscoveryApps, tab]);

  const closeDetailModal = () => {
    setDetailOpen(false);
    setDetailKey(null);
    setDetailSummary(null);
    setDetailLoading(false);
    setDetailError(undefined);
    setDetailApp(null);
  };

  const openDiscoveryAppDetail = useCallback((app: FoxelCoreApp) => {
    setDetailOpen(true);
    setDetailKey(app.key);
    setDetailSummary(app);
    setDetailError(undefined);
    setDetailApp(null);
  }, []);

  useEffect(() => {
    if (!detailOpen || !detailKey) return;

    let cancelled = false;
    const currentKey = detailKey;

    const run = async () => {
      setDetailLoading(true);
      setDetailError(undefined);
      try {
        const app = await fetchFoxelCoreAppDetail(currentKey);
        if (cancelled) return;
        setDetailApp(app);
      } catch (e: any) {
        if (cancelled) return;
        setDetailError(e?.message || t('Load failed'));
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [detailKey, detailOpen, detailReloadId, t]);

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
  const resolvePluginTexts = useCallback((p: PluginItem): { name?: string; description?: string } => {
    const i18n = (p.manifest as any)?.i18n as any;
    const entry = i18n?.[lang] as any;
    return {
      name: entry?.name || p.name || undefined,
      description: entry?.description || p.description || undefined,
    };
  }, [lang]);

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
  }, [data, q, resolvePluginTexts]);

  // 过滤应用发现列表
  const filteredDiscoveryApps = useMemo(() => {
    const s = discoverySearch.trim().toLowerCase();
    if (!s) return discoveryApps;
    return discoveryApps.filter(app => {
      const name = (lang === 'zh' ? app.name.zh : app.name.en).toLowerCase();
      const desc = (lang === 'zh' ? app.description.zh : app.description.en).toLowerCase();
      const author = (app.author || '').toLowerCase();
      const tags = lang === 'zh' ? app.tags.zh : app.tags.en;
      return (
        name.includes(s) ||
        desc.includes(s) ||
        author.includes(s) ||
        tags.some(tag => tag.toLowerCase().includes(s)) ||
        app.key.toLowerCase().includes(s)
      );
    });
  }, [discoveryApps, discoverySearch, lang]);

  // 检查应用是否已安装
  const isAppInstalled = (appKey: string) => {
    return data.some(p => p.key === appKey);
  };

  // 下载并安装应用
  const handleDownloadAndInstall = async (app: Pick<FoxelCoreApp, 'key' | 'version' | 'downloadUrl'>) => {
    if (downloadingApps.has(app.key)) return;
    
    try {
      setDownloadingApps(prev => new Set(prev).add(app.key));
      message.loading({ content: t('Downloading'), key: app.key, duration: 0 });
      
      const file = await downloadFoxelCoreApp(app);
      message.destroy(app.key);
      message.loading({ content: t('Installing'), key: app.key, duration: 0 });
      
      const result = await pluginsApi.install(file);
      message.destroy(app.key);
      
      if (result.success) {
        message.success(t('Installed successfully'));
        await reload();
        await reloadPluginApps();
      } else {
        message.error(result.message || t('Installation failed'));
      }
    } catch (e: any) {
      message.destroy(app.key);
      message.error(e?.message || t('Installation failed'));
    } finally {
      setDownloadingApps(prev => {
        const next = new Set(prev);
        next.delete(app.key);
        return next;
      });
    }
  };

  const renderCard = (p: PluginItem) => {
    const texts = resolvePluginTexts(p);
    const icon = resolvePluginIcon(p);
    const name = texts.name || `${t('Plugin')} ${p.key}`;
    const appKey = `plugin:${p.key}`;
    const app = getAppByKey(appKey);
    const canOpenApp = !!p.open_app;
    return (
      <CenterCard
        key={p.key}
        iconUrl={icon}
        iconAlt={name}
        name={name}
        version={p.version || undefined}
        description={texts.description || t('No description')}
        metaLeft={p.author || undefined}
        metaRight={p.key}
        pills={buildCardPills(p.supported_exts, t('Any'))}
        footerLeft={(p.github || p.website) ? (
          <div className="fx-center-card-links">
            {p.github ? (
              <a className="fx-center-card-iconLink" href={p.github || undefined} target="_blank" rel="noreferrer" title="GitHub" aria-label="GitHub">
                <GithubOutlined />
              </a>
            ) : null}
            {p.website ? (
              <a className="fx-center-card-iconLink" href={p.website || undefined} target="_blank" rel="noreferrer" title={t('Website')} aria-label={t('Website')}>
                <LinkOutlined />
              </a>
            ) : null}
          </div>
        ) : null}
        footerRight={
          <div className="fx-center-card-actions">
            <Button
              type="primary"
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
            </Button>
            <Popconfirm title={t('Confirm delete this plugin?')} onConfirm={async () => { await pluginsApi.remove(p.key); await reload(); await reloadPluginApps(); }}>
              <Button type="text" danger size="small">{t('Uninstall')}</Button>
            </Popconfirm>
          </div>
        }
      />
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
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, justifyContent: 'start' }}>
                      {Array.from({ length: 6 }).map((_, i) => (
                        <Card key={i} style={{ borderRadius: 10 }}>
                          <Skeleton active avatar paragraph={{ rows: 3 }} />
                        </Card>
                      ))}
                    </div>
                  ) : filtered.length === 0 ? (
                    <Empty description={t('No plugins')} />
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, justifyContent: 'start' }}>
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
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <input
                    type="text"
                    placeholder={t('Search apps')}
                    value={discoverySearch}
                    onChange={e => setDiscoverySearch(e.target.value)}
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
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={loadDiscoveryApps}
                    loading={discoveryLoading}
                  >
                    {t('Refresh')}
                  </Button>
                </div>
                <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 4 }}>
                  {discoveryLoading && discoveryApps.length === 0 ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, justifyContent: 'start' }}>
                      {Array.from({ length: 6 }).map((_, i) => (
                        <Card key={i} style={{ borderRadius: 10 }}>
                          <Skeleton active avatar paragraph={{ rows: 3 }} />
                        </Card>
                      ))}
                    </div>
                  ) : discoveryError ? (
                    <Empty description={discoveryError}>
                      <Button onClick={loadDiscoveryApps}>{t('Refresh')}</Button>
                    </Empty>
                  ) : filteredDiscoveryApps.length === 0 ? (
                    <Empty description={discoveryApps.length === 0 ? t('No results') : t('No results')} />
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, justifyContent: 'start' }}>
                      {filteredDiscoveryApps.map(app => {
                        const name = lang === 'zh' ? app.name.zh : app.name.en;
                        const description = lang === 'zh' ? app.description.zh : app.description.en;
                        const tags = lang === 'zh' ? app.tags.zh : app.tags.en;
                        const iconUrl = `https://foxel.cc/api/apps/${encodeURIComponent(app.key)}/icon`;
                        const installed = isAppInstalled(app.key);
                        const downloading = downloadingApps.has(app.key);
                        const approvedDate = new Date(app.approvedAt).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US');
                        const onOpenDetail = () => openDiscoveryAppDetail(app);
                        
                        return (
                          <CenterCard
                            key={app.key}
                            iconUrl={iconUrl}
                            iconAlt={name}
                            name={name}
                            version={app.version || undefined}
                            description={description}
                            metaLeft={app.author || undefined}
                            metaRight={lang === 'zh' ? `审核于 ${approvedDate}` : `Approved ${approvedDate}`}
                            pills={buildCardPills(tags)}
                            onIconClick={onOpenDetail}
                            onTitleClick={onOpenDetail}
                            footerLeft={app.website ? (
                              <a className="fx-center-card-iconLink" href={app.website} target="_blank" rel="noreferrer" title={t('Website')} aria-label={t('Website')}>
                                <LinkOutlined />
                              </a>
                            ) : null}
                            footerRight={installed ? (
                              <span className="fx-center-pill fx-center-pill-success">{t('Installed already')}</span>
                            ) : (
                              <Button
                                type="primary"
                                size="small"
                                icon={<DownloadOutlined />}
                                loading={downloading}
                                onClick={() => handleDownloadAndInstall(app)}
                              >
                                {downloading ? t('Downloading') : t('Download and Install')}
                              </Button>
                            )}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )
          }
        ]}
      />

      <Modal
        title={(() => {
          if (detailApp) {
            return `${lang === 'zh' ? detailApp.latest.name.zh : detailApp.latest.name.en} · ${t('Details')}`;
          }
          if (detailSummary) {
            return `${lang === 'zh' ? detailSummary.name.zh : detailSummary.name.en} · ${t('Details')}`;
          }
          return t('Details');
        })()}
        open={detailOpen}
        onCancel={closeDetailModal}
        width={860}
        footer={(() => {
          const key = detailKey || detailApp?.key || detailSummary?.key;
          const installed = key ? isAppInstalled(key) : false;
          const downloading = key ? downloadingApps.has(key) : false;
          const downloadUrl = detailApp?.latest.downloadUrl || detailSummary?.downloadUrl;
          const version = detailApp?.latest.version || detailSummary?.version;

          return (
            <Space>
              <Button onClick={closeDetailModal}>{t('Close')}</Button>
              {installed ? (
                <Button disabled>{t('Installed already')}</Button>
              ) : (
                <Button
                  type="primary"
                  size="middle"
                  icon={<DownloadOutlined />}
                  loading={downloading}
                  disabled={!key || !downloadUrl || !version || detailLoading}
                  onClick={() => {
                    if (!key || !downloadUrl || !version) return;
                    void handleDownloadAndInstall({ key, version, downloadUrl });
                  }}
                >
                  {t('Download and Install')}
                </Button>
              )}
            </Space>
          );
        })()}
      >
        <div style={{ maxHeight: '70vh', overflowY: 'auto', paddingRight: 6 }}>
          {detailLoading && !detailApp ? (
            <Skeleton active avatar paragraph={{ rows: 8 }} />
          ) : detailError ? (
            <Empty description={detailError}>
              <Button
                onClick={() => {
                  if (!detailKey) return;
                  setDetailApp(null);
                  setDetailError(undefined);
                  setDetailReloadId(v => v + 1);
                }}
              >
                {t('Refresh')}
              </Button>
            </Empty>
          ) : detailApp ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ width: 64, height: 64, borderRadius: 14, overflow: 'hidden', border: `1px solid ${token.colorBorder}` }}>
                  <img
                    src={`https://foxel.cc/api/apps/${encodeURIComponent(detailApp.key)}/icon`}
                    alt={lang === 'zh' ? detailApp.latest.name.zh : detailApp.latest.name.en}
                    style={{ width: '100%', height: '100%', objectFit: 'contain', background: token.colorBgContainer }}
                    loading="lazy"
                    onError={(e) => { (e.currentTarget as HTMLImageElement).src = '/logo.svg'; }}
                  />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
                    <Typography.Title level={5} style={{ margin: 0 }}>
                      {lang === 'zh' ? detailApp.latest.name.zh : detailApp.latest.name.en}
                    </Typography.Title>
                    <Typography.Text type="secondary">
                      {t('Version')}: {detailApp.latest.version}
                    </Typography.Text>
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 10, color: token.colorTextTertiary, fontSize: 12 }}>
                    <span>{detailApp.latest.author}</span>
                    <span>{detailApp.key}</span>
                    <span>
                      {lang === 'zh'
                        ? `审核于 ${new Date(detailApp.latest.approvedAt).toLocaleDateString('zh-CN')}`
                        : `Approved ${new Date(detailApp.latest.approvedAt).toLocaleDateString('en-US')}`}
                    </span>
                    {detailApp.latest.website ? (
                      <a href={detailApp.latest.website} target="_blank" rel="noreferrer" style={{ color: token.colorTextTertiary }}>
                        <LinkOutlined style={{ marginRight: 6 }} />
                        {t('Website')}
                      </a>
                    ) : null}
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <Space size={[4, 4]} wrap>
                      {(lang === 'zh' ? detailApp.latest.tags.zh : detailApp.latest.tags.en).map(tag => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </div>
                </div>
              </div>

              <Tabs
                defaultActiveKey="details"
                items={[
                  {
                    key: 'details',
                    label: t('Details'),
                    children: (
                      <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                        {lang === 'zh' ? detailApp.latest.description.zh : detailApp.latest.description.en}
                      </Typography.Paragraph>
                    ),
                  },
                  {
                    key: 'versions',
                    label: t('Version'),
                    children: (
                      <Collapse
                        size="small"
                        items={detailApp.versions.map(v => {
                          const approvedDate = new Date(v.approvedAt).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US');
                          return {
                            key: v.version,
                            label: (
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v.version}</span>
                                <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>
                                  {lang === 'zh' ? `审核于 ${approvedDate}` : `Approved ${approvedDate}`}
                                </span>
                              </div>
                            ),
                            children: v.releaseNotesMd ? (
                              <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                                <ReactMarkdown>{v.releaseNotesMd}</ReactMarkdown>
                              </div>
                            ) : (
                              <Typography.Text type="secondary">
                                {lang === 'zh' ? '暂无更新记录' : 'No release notes'}
                              </Typography.Text>
                            ),
                          };
                        })}
                        style={{ background: 'transparent' }}
                      />
                    ),
                  },
                ]}
              />
            </div>
          ) : (
            <Empty description={t('No results')} />
          )}
        </div>
      </Modal>

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
