import { Alert, Button, Form, Select, Switch, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { rolesApi, type RoleInfo } from '../../../api/roles';
import { useI18n } from '../../../i18n';

interface AuthSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
}

export default function AuthSettingsTab({
  config,
  loading,
  onSave,
}: AuthSettingsTabProps) {
  const { t } = useI18n();
  const [rolesLoading, setRolesLoading] = useState(false);
  const [roles, setRoles] = useState<RoleInfo[]>([]);

  useEffect(() => {
    let mounted = true;
    async function loadRoles() {
      setRolesLoading(true);
      try {
        const list = await rolesApi.list();
        if (!mounted) return;
        setRoles(list);
      } catch (e: any) {
        message.error(e.message || t('Load failed'));
      } finally {
        if (mounted) setRolesLoading(false);
      }
    }
    loadRoles();
    return () => {
      mounted = false;
    };
  }, [t]);

  const initialValues = useMemo(() => {
    const allowRegister = (config.AUTH_ALLOW_REGISTER || '').trim().toLowerCase() === 'true';
    const roleIdRaw = (config.AUTH_DEFAULT_REGISTER_ROLE_ID || '').trim();
    const roleId = roleIdRaw ? Number(roleIdRaw) : undefined;
    return {
      AUTH_ALLOW_REGISTER: allowRegister,
      AUTH_DEFAULT_REGISTER_ROLE_ID: Number.isFinite(roleId) ? roleId : undefined,
    };
  }, [config]);

  return (
    <Form
      layout="vertical"
      initialValues={initialValues}
      onFinish={async (vals) => {
        const allow = !!vals.AUTH_ALLOW_REGISTER;
        const payload: Record<string, unknown> = {
          AUTH_ALLOW_REGISTER: allow ? 'true' : 'false',
        };
        if (allow) {
          payload.AUTH_DEFAULT_REGISTER_ROLE_ID = String(vals.AUTH_DEFAULT_REGISTER_ROLE_ID);
        }
        await onSave(payload);
      }}
      style={{ marginTop: 24 }}
      key={'auth-settings-' + (config.AUTH_ALLOW_REGISTER ?? '') + '-' + (config.AUTH_DEFAULT_REGISTER_ROLE_ID ?? '')}
    >
      <Alert
        type="info"
        showIcon
        message={t('Enabling registration allows new users to sign up and assigns them the default role')}
        style={{ marginBottom: 16 }}
      />

      <Form.Item
        name="AUTH_ALLOW_REGISTER"
        label={t('Enable Registration')}
        valuePropName="checked"
      >
        <Switch />
      </Form.Item>

      <Form.Item dependencies={['AUTH_ALLOW_REGISTER']} noStyle>
        {({ getFieldValue }) => {
          const enabled = !!getFieldValue('AUTH_ALLOW_REGISTER');
          return (
            <Form.Item
              name="AUTH_DEFAULT_REGISTER_ROLE_ID"
              label={t('Default Role for New Registrations')}
              rules={enabled ? [{ required: true, message: t('Please select default role') }] : []}
            >
              <Select
                size="large"
                loading={rolesLoading}
                disabled={!enabled || rolesLoading}
                placeholder={t('Select roles')}
                options={roles.map((r) => ({ value: r.id, label: r.name }))}
              />
            </Form.Item>
          );
        }}
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>
          {t('Save')}
        </Button>
      </Form.Item>
    </Form>
  );
}

