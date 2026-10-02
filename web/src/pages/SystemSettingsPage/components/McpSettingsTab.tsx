import { useState } from 'react';
import { ApiOutlined, CopyOutlined } from '@ant-design/icons';
import { Button, Input, message, Switch, Tag, Tooltip, Typography } from 'antd';
import { API_BASE_URL } from '../../../api/client';
import { useAuth } from '../../../contexts/AuthContext';
import { useI18n } from '../../../i18n';

interface McpSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<boolean>;
}

export default function McpSettingsTab({ config, loading, onSave }: McpSettingsTabProps) {
  const { t } = useI18n();
  const { token, user } = useAuth();
  const [saving, setSaving] = useState(false);
  const enabled = ['1', 'true', 'yes', 'on'].includes((config.MCP_ENABLED ?? '1').trim().toLowerCase());
  const domain = (config.APP_DOMAIN ?? '').trim();
  const baseUrl = domain
    ? `${/^https?:\/\//i.test(domain) ? domain : `https://${domain}`}`.replace(/\/+$/, '') + '/api'
    : new URL(API_BASE_URL, window.location.origin).href.replace(/\/+$/, '');
  const endpoint = `${baseUrl}/mcp/`;
  const connectionConfig = (credential: string) => JSON.stringify({
    mcpServers: {
      foxel: { url: endpoint, headers: { Authorization: `Bearer ${credential}` } },
    },
  }, null, 2);

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      message.success(t('Copied'));
    } catch {
      message.error(t('Copy failed'));
    }
  };

  const toggle = async (checked: boolean) => {
    setSaving(true);
    try {
      await onSave({ MCP_ENABLED: checked ? '1' : '0' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fx-mcp-settings">
      <section className="fx-mcp-overview">
        <div className="fx-mcp-heading">
          <div className="fx-mcp-icon"><ApiOutlined /></div>
          <div>
            <div className="fx-mcp-title">
              <Typography.Title level={4}>{t('Foxel MCP')}</Typography.Title>
              <Tag color={enabled ? 'success' : 'default'}>{t(enabled ? 'Enabled' : 'Disabled')}</Tag>
            </div>
            <Typography.Paragraph type="secondary">{t('Connect MCP clients to your Foxel files, search, and processors.')}</Typography.Paragraph>
          </div>
        </div>
        <div className="fx-mcp-endpoint">
          <Typography.Text type="secondary">{t('Remote MCP Endpoint')}</Typography.Text>
          <div className="fx-mcp-code-row">
            <code>{endpoint}</code>
            <Tooltip title={t('Copy endpoint')}>
              <Button type="text" icon={<CopyOutlined />} aria-label={t('Copy endpoint')} onClick={() => copy(endpoint)} />
            </Tooltip>
          </div>
          <Typography.Text type="secondary">{t('Streamable HTTP with Foxel Bearer Token authentication.')}</Typography.Text>
        </div>
      </section>

      <section className="fx-settings-section">
        <h3>{t('Permissions')}</h3>
        <div className="fx-mcp-permission-row">
          <div>
            <Typography.Text strong>{t('Enable MCP')}</Typography.Text>
            <Typography.Paragraph type="secondary">{t('Allow external MCP clients to connect. Disabling this does not affect the built-in AI agent.')}</Typography.Paragraph>
          </div>
          <Switch checked={enabled} loading={saving} disabled={loading} onChange={toggle} aria-label={t('Enable MCP')} />
        </div>
        <div className="fx-mcp-permission-info">
          <Typography.Text strong>{t('Account permissions')}</Typography.Text>
          <Typography.Paragraph type="secondary">{t('MCP follows the authenticated account’s read, write, and delete permissions. External clients handle confirmation for write operations.')}</Typography.Paragraph>
        </div>
      </section>

      <section className="fx-settings-section">
        <h3>{t('Access Token')}</h3>
        <Typography.Paragraph type="secondary">{t('This token belongs to your current account and grants its existing permissions. Keep it private.')}</Typography.Paragraph>
        <div className="fx-mcp-token-row">
          <Input.Password value={token ?? ''} readOnly autoComplete="off" aria-label={t('Access Token')} />
          <Tooltip title={t('Copy token')}>
            <Button icon={<CopyOutlined />} disabled={!token} aria-label={t('Copy token')} onClick={() => token && copy(token)} />
          </Tooltip>
        </div>
        {user && <Typography.Text type="secondary">{t('Account')}: {user.username}</Typography.Text>}
      </section>

      <section className="fx-settings-section">
        <div className="fx-mcp-config-heading">
          <h3>{t('Connection configuration')}</h3>
          <Tooltip title={t('Copy configuration including your token')}>
            <Button icon={<CopyOutlined />} disabled={!token} aria-label={t('Copy configuration including your token')} onClick={() => token && copy(connectionConfig(token))} />
          </Tooltip>
        </div>
        <pre className="fx-mcp-config"><code>{connectionConfig('YOUR_FOXEL_TOKEN')}</code></pre>
      </section>
    </div>
  );
}
