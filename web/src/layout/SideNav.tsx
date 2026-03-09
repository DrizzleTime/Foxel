import { Layout, Menu, theme, Button, Modal, Tag, Tooltip, Descriptions, Alert, Divider, Spin, Drawer } from 'antd';
import { navGroups } from './nav.ts';
import type { NavItem, NavGroup } from './nav.ts';
import { memo, useEffect, useState, useMemo } from 'react';
import { useSystemStatus } from '../contexts/SystemContext.tsx';
import {
  CheckCircleOutlined,
  FileTextOutlined,
  GithubOutlined,
  MenuFoldOutlined,
  SendOutlined,
  WechatOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import '../styles/sider-menu.css';
import { getLatestVersion } from '../api/config.ts';
import ReactMarkdown from 'react-markdown';
import { useTheme } from '../contexts/ThemeContext';
import { useI18n } from '../i18n';
import { useAppWindows } from '../contexts/AppWindowsContext';
import WeChatModal from '../components/WeChatModal';
import { useAuth } from '../contexts/AuthContext';

const { Sider } = Layout;

export interface SideNavProps {
  collapsed: boolean;
  onToggle(): void;
  activeKey: string;
  onChange(key: string): void;
  mobile?: boolean;
  open?: boolean;
  onClose?: () => void;
}

const SideNav = memo(function SideNav({
  collapsed,
  activeKey,
  onChange,
  onToggle,
  mobile = false,
  open = false,
  onClose,
}: SideNavProps) {
  const status = useSystemStatus();
  const { token } = theme.useToken();
  const { resolvedMode } = useTheme();
  const { t } = useI18n();
  const { user } = useAuth();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isVersionModalOpen, setIsVersionModalOpen] = useState(false);
  const [latestVersion, setLatestVersion] = useState<{
    version: string;
    body: string;
  } | null>(null);

  const filteredNavGroups = useMemo(() => {
    const isAdmin = user?.is_admin ?? false;
    return navGroups
      .map((group) => ({
        ...group,
        children: group.children.filter((item) => (!item.adminOnly || isAdmin) && !(mobile && item.hideOnMobile)),
      }))
      .filter((group) => group.children.length > 0);
  }, [mobile, user]);

  useEffect(() => {
    getLatestVersion().then((resp) => {
      if (resp.latest_version && resp.body) {
        setLatestVersion({
          version: resp.latest_version,
          body: resp.body,
        });
      }
    });
  }, []);

  const hasUpdate = latestVersion && latestVersion.version !== status?.version;
  const { windows, restoreWindow } = useAppWindows();
  const minimized = windows.filter((w) => w.minimized);
  const DEFAULT_APP_ICON =
    'data:image/svg+xml;utf8,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
         <rect x="3" y="3" width="18" height="18" rx="4" ry="4" fill="currentColor" />
         <rect x="7" y="7" width="10" height="10" rx="2" ry="2" fill="#fff"/>
       </svg>`,
    );
  const currentCollapsed = mobile ? false : collapsed;

  const handleChange = (key: string) => {
    onChange(key);
    if (mobile) {
      onClose?.();
    }
  };

  const renderNavBody = (bodyCollapsed: boolean, showCollapseButton: boolean) => (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: bodyCollapsed ? 'center' : 'space-between',
          padding: '0 14px',
          fontWeight: 600,
          fontSize: 18,
          letterSpacing: 0.5,
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
          <img
            src={status?.logo}
            alt="Foxel"
            style={{
              width: 24,
              height: 24,
              objectFit: 'contain',
              marginRight: bodyCollapsed ? 0 : 8,
              ...(resolvedMode === 'dark'
                ? { filter: 'brightness(0) invert(1)' }
                : status?.logo?.endsWith('.svg')
                  ? { filter: 'brightness(0) saturate(100%)' }
                  : {}),
            }}
          />
          {!bodyCollapsed && (
            <span
              style={{
                fontWeight: 700,
                color: resolvedMode === 'dark' ? '#fff' : token.colorText,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {status?.title}
            </span>
          )}
        </div>
        {showCollapseButton && !bodyCollapsed && (
          <Button type="text" icon={<MenuFoldOutlined />} onClick={onToggle} style={{ fontSize: 18 }} />
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '4px 4px 8px' }}>
        {filteredNavGroups.map((group: NavGroup) => (
          <div key={group.key} style={{ marginBottom: 12 }}>
            {!!group.title && !bodyCollapsed && (
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: 0.5,
                  padding: '6px 10px 4px',
                  color: token.colorTextTertiary,
                  textTransform: 'uppercase',
                }}
              >
                {t(group.title)}
              </div>
            )}
            <Menu
              mode="inline"
              selectable
              inlineIndent={12}
              inlineCollapsed={!mobile && bodyCollapsed}
              selectedKeys={[activeKey]}
              onClick={(e) => handleChange(e.key)}
              items={group.children.map((i: NavItem) => ({ key: i.key, icon: i.icon, label: t(i.label) }))}
              style={{ borderInline: 'none', background: 'transparent' }}
              className="sider-menu-group foxel-sider-menu"
            />
          </div>
        ))}
      </div>

      <div
        style={{
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          flexShrink: 0,
          borderTop: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        {!bodyCollapsed && minimized.length > 0 && (
          <div
            style={{
              width: '100%',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
            }}
          >
            {minimized.map((w) => {
              const src = w.app.iconUrl || DEFAULT_APP_ICON;
              const title = w.kind === 'file' ? `${w.app.name} - ${w.entry?.name || ''}` : w.app.name;
              return (
                <Tooltip key={w.id} title={title} placement={bodyCollapsed ? 'right' : 'top'}>
                  <Button
                    shape="circle"
                    onClick={() => restoreWindow(w.id)}
                    icon={<img src={src} alt={w.app.name} style={{ width: 16, height: 16 }} />}
                  />
                </Tooltip>
              );
            })}
          </div>
        )}

        <div
          style={{
            fontSize: 12,
            color: token.colorTextSecondary,
            textAlign: 'center',
            height: 22,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
          onClick={() => setIsVersionModalOpen(true)}
        >
          {hasUpdate ? (
            <Tooltip title={t('New version found: {version}', { version: latestVersion?.version || '' })} placement={bodyCollapsed ? 'right' : 'top'}>
              <a rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                {bodyCollapsed ? (
                  <Tag icon={<WarningOutlined />} color="warning" style={{ marginInlineEnd: 0 }} />
                ) : (
                  <Tag icon={<WarningOutlined />} color="warning">
                    {t('Update available')} [{latestVersion?.version}]
                  </Tag>
                )}
              </a>
            </Tooltip>
          ) : latestVersion ? (
            <Tooltip title={t('You are on the latest: {version}', { version: status?.version || '' })} placement={bodyCollapsed ? 'right' : 'top'}>
              {bodyCollapsed ? (
                <Tag icon={<CheckCircleOutlined />} color="success" style={{ marginInlineEnd: 0 }} />
              ) : (
                <Tag icon={<CheckCircleOutlined />} color="success">
                  {status?.version}
                </Tag>
              )}
            </Tooltip>
          ) : (
            !bodyCollapsed && <Tag>{status?.version}</Tag>
          )}
        </div>

        {!bodyCollapsed && (
          <div style={{ display: 'flex', flexDirection: 'row', gap: 8 }}>
            <Button shape="circle" icon={<GithubOutlined />} href="https://github.com/DrizzleTime/Foxel" target="_blank" />
            <Button shape="circle" icon={<WechatOutlined />} onClick={() => setIsModalOpen(true)} />
            <Button shape="circle" icon={<SendOutlined />} href="https://t.me/+thDsBfyqJxZkNTU1" target="_blank" />
            <Button shape="circle" icon={<FileTextOutlined />} href="https://foxel.cc" target="_blank" />
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {mobile ? (
        <Drawer
          placement="left"
          open={open}
          onClose={onClose}
          title={null}
          width={280}
          styles={{ body: { padding: 0 } }}
        >
          {renderNavBody(false, false)}
        </Drawer>
      ) : (
        <Sider
          collapsedWidth={60}
          collapsible
          trigger={null}
          collapsed={collapsed}
          width={208}
          style={{
            background: token.colorBgContainer,
            borderRight: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          {renderNavBody(currentCollapsed, true)}
        </Sider>
      )}

      <WeChatModal open={isModalOpen} onClose={() => setIsModalOpen(false)} />
      <Modal
        open={isVersionModalOpen}
        onCancel={() => setIsVersionModalOpen(false)}
        title={t('Version Info')}
        footer={null}
        width={600}
      >
        <div style={{ paddingTop: 12 }}>
          {latestVersion ? (
            <>
              <Descriptions bordered column={1} size="small">
                <Descriptions.Item label={t('Current Version')}>
                  <Tag>{status?.version}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('Latest Version')}>
                  <Tag color={hasUpdate ? 'orange' : 'green'}>{latestVersion.version}</Tag>
                </Descriptions.Item>
              </Descriptions>

              {hasUpdate && (
                <Alert
                  message={<span style={{ color: token.colorText }}>{t('New version found: {version}', { version: latestVersion.version })}</span>}
                  description={<span style={{ color: token.colorTextSecondary }}>{t('Please update to the latest for features and fixes')}</span>}
                  type="info"
                  showIcon
                  style={{ marginTop: 24, marginBottom: 24, background: token.colorInfoBg, borderColor: token.colorInfoBorder }}
                  action={
                    <Button
                      size="small"
                      type="primary"
                      href="https://github.com/DrizzleTime/Foxel/releases"
                      target="_blank"
                      icon={<GithubOutlined />}
                    >
                      {t('Open Releases')}
                    </Button>
                  }
                />
              )}

              <Divider titlePlacement="left" plain>
                {t('Changelog')}
              </Divider>
              <div
                style={{
                  maxHeight: '40vh',
                  overflowY: 'auto',
                  padding: '8px 16px',
                  background: token.colorFillAlter,
                  borderRadius: token.borderRadiusLG,
                  border: `1px solid ${token.colorBorderSecondary}`,
                }}
              >
                <ReactMarkdown
                  components={{
                    h3: ({ ...props }) => (
                      <h3
                        style={{
                          fontSize: 16,
                          borderBottom: `1px solid ${token.colorBorderSecondary}`,
                          paddingBottom: 8,
                          marginTop: 24,
                          marginBottom: 16,
                          color: token.colorTextHeading,
                        }}
                        {...props}
                      />
                    ),
                    ul: ({ ...props }) => <ul style={{ paddingLeft: 20 }} {...props} />,
                    li: ({ ...props }) => <li style={{ marginBottom: 8 }} {...props} />,
                    p: ({ ...props }) => <p style={{ marginBottom: 8 }} {...props} />,
                    a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                  }}
                >
                  {latestVersion.body}
                </ReactMarkdown>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0', color: token.colorTextSecondary }}>
              <Spin size="large" />
              <p style={{ marginTop: 16 }}>{t('Fetching latest version...')}</p>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
});

export default SideNav;
