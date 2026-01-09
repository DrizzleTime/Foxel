import { Layout, Button, Dropdown, theme, Flex, Avatar, Typography, Tooltip } from 'antd';
import { SearchOutlined, MenuUnfoldOutlined, LogoutOutlined, UserOutlined, RobotOutlined } from '@ant-design/icons';
import { memo, useState } from 'react';
import SearchDialog from './SearchDialog.tsx';
import { authApi } from '../api/auth.ts';
import { useNavigate } from 'react-router';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { useAuth } from '../contexts/AuthContext';
import ProfileModal from '../components/ProfileModal';

const { Header } = Layout;

export interface TopHeaderProps {
  collapsed: boolean;
  onToggle(): void;
  onOpenAiAgent(): void;
}

const TopHeader = memo(function TopHeader({ collapsed, onToggle, onOpenAiAgent }: TopHeaderProps) {
  const { token } = theme.useToken();
  const [searchOpen, setSearchOpen] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { user } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);

  const handleLogout = () => {
    authApi.logout();
    navigate('/login', { replace: true });
  };

  const openProfile = () => setProfileOpen(true);

  return (
    <Header style={{ background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}`, display: 'flex', alignItems: 'center', gap: 16, backdropFilter: 'saturate(180%) blur(8px)' }}>
      {collapsed && (
        <Button
          type="text"
          icon={<MenuUnfoldOutlined />}
          onClick={onToggle}
          style={{ fontSize: 18, marginRight: 8 }}
        />
      )}
      <Button
        icon={<SearchOutlined />}
        style={{ maxWidth: 420 }}
        onClick={() => setSearchOpen(true)}
      >
        {t('Search files / tags / types')}
      </Button>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      <Flex style={{ marginLeft: 'auto' }} align="center" gap={12}>
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
              { key: 'logout', label: t('Log Out'), icon: <LogoutOutlined />, onClick: handleLogout }
            ]
          }}
        >
          <Button type="text" style={{ paddingInline: 8, height: 40 }}>
            <Flex align="center" gap={8}>
              <Avatar size={28} src={user?.gravatar_url}>
                {(user?.full_name || user?.username || 'A').charAt(0).toUpperCase()}
              </Avatar>
              <Typography.Text style={{ maxWidth: 160 }} ellipsis>
                {user?.full_name || user?.username || t('Admin')}
              </Typography.Text>
            </Flex>
          </Button>
        </Dropdown>
        <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
      </Flex>
    </Header>
  );
});

export default TopHeader;
