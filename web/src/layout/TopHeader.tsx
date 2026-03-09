import { Layout, Button, Dropdown, theme, Flex, Avatar, Typography, Tooltip } from 'antd';
import { SearchOutlined, MenuUnfoldOutlined, LogoutOutlined, UserOutlined, RobotOutlined, BellOutlined } from '@ant-design/icons';
import { memo, useState } from 'react';
import SearchDialog from './SearchDialog.tsx';
import { authApi } from '../api/auth.ts';
import { useNavigate } from 'react-router';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { useAuth } from '../contexts/AuthContext';
import ProfileModal from '../components/ProfileModal';
import NoticesModal from '../components/NoticesModal';
import { useSystemStatus } from '../contexts/SystemContext';
import useResponsive from '../hooks/useResponsive';

const { Header } = Layout;

export interface TopHeaderProps {
  collapsed: boolean;
  onToggle(): void;
  onOpenAiAgent(): void;
  showMenuButton?: boolean;
}

const TopHeader = memo(function TopHeader({ collapsed, onToggle, onOpenAiAgent, showMenuButton }: TopHeaderProps) {
  const { token } = theme.useToken();
  const [searchOpen, setSearchOpen] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { user } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const [noticesOpen, setNoticesOpen] = useState(false);
  const status = useSystemStatus();
  const { isMobile } = useResponsive();

  const handleLogout = () => {
    authApi.logout();
    navigate('/login', { replace: true });
  };

  const openProfile = () => setProfileOpen(true);

  return (
    <Header
      style={{
        background: token.colorBgContainer,
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        alignItems: 'center',
        gap: isMobile ? 8 : 16,
        paddingInline: isMobile ? 12 : 16,
        minWidth: 0,
        backdropFilter: 'saturate(180%) blur(8px)',
      }}
    >
      {showMenuButton && (
        <Button
          type="text"
          icon={<MenuUnfoldOutlined />}
          onClick={onToggle}
          style={{ fontSize: 18, marginRight: isMobile ? 0 : 8 }}
          aria-label={collapsed ? t('Open menu') : t('Collapse menu')}
        />
      )}

      <Button
        icon={<SearchOutlined />}
        style={{ maxWidth: isMobile ? 40 : 420, minWidth: isMobile ? 40 : undefined, paddingInline: isMobile ? 0 : undefined }}
        onClick={() => setSearchOpen(true)}
        aria-label={t('Search files / tags / types')}
      >
        {!isMobile && t('Search files / tags / types')}
      </Button>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />

      <Flex style={{ marginLeft: 'auto', minWidth: 0 }} align="center" gap={isMobile ? 4 : 12}>
        <Tooltip title={t('Notices')}>
          <Button
            type="text"
            icon={<BellOutlined />}
            aria-label={t('Notices')}
            onClick={() => setNoticesOpen(true)}
            style={{ paddingInline: 8, height: 40 }}
          />
        </Tooltip>
        <Tooltip title={t('AI Agent')}>
          <Button
            type="text"
            icon={<RobotOutlined />}
            aria-label={t('AI Agent')}
            onClick={onOpenAiAgent}
            style={{ paddingInline: 8, height: 40 }}
          />
        </Tooltip>
        <LanguageSwitcher />
        <Dropdown
          menu={{
            items: [
              { key: 'profile', label: t('Profile'), icon: <UserOutlined />, onClick: openProfile },
              { key: 'logout', label: t('Log Out'), icon: <LogoutOutlined />, onClick: handleLogout },
            ],
          }}
        >
          <Button type="text" style={{ paddingInline: 8, height: 40 }}>
            <Flex align="center" gap={8}>
              <Avatar size={28} src={user?.gravatar_url}>
                {(user?.full_name || user?.username || 'A').charAt(0).toUpperCase()}
              </Avatar>
              {!isMobile && (
                <Typography.Text style={{ maxWidth: 160 }} ellipsis>
                  {user?.full_name || user?.username || t('Admin')}
                </Typography.Text>
              )}
            </Flex>
          </Button>
        </Dropdown>
        <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
        <NoticesModal open={noticesOpen} onClose={() => setNoticesOpen(false)} version={status?.version || ''} />
      </Flex>
    </Header>
  );
});

export default TopHeader;
