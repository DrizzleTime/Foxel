import { Alert, Button, Divider, Form, Input, Select, Switch, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { rolesApi, type RoleInfo } from '../../../api/roles';
import { useI18n } from '../../../i18n';

interface AppConfigKey {
  key: string;
  label: string;
  default?: string;
}

interface AppSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
  configKeys: AppConfigKey[];
}

export default function AppSettingsTab({
  config,
  loading,
  onSave,
  configKeys,
}: AppSettingsTabProps) {
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
      ...Object.fromEntries(configKeys.map(({ key, default: def }) => [key, config[key] ?? def ?? ''])),
      AUTH_ALLOW_REGISTER: allowRegister,
      AUTH_DEFAULT_REGISTER_ROLE_ID: Number.isFinite(roleId) ? roleId : undefined,
    };
  }, [config, configKeys]);

  return (
    <Form
      layout="vertical"
      initialValues={initialValues}
      onFinish={async (vals) => {
        const payload: Record<string, unknown> = {};
        for (const { key } of configKeys) {
          payload[key] = vals[key];
        }
        const allow = !!vals.AUTH_ALLOW_REGISTER;
        payload.AUTH_ALLOW_REGISTER = allow ? 'true' : 'false';
        if (allow) {
          payload.AUTH_DEFAULT_REGISTER_ROLE_ID = String(vals.AUTH_DEFAULT_REGISTER_ROLE_ID);
        }
        await onSave(payload);
      }}
      style={{ marginTop: 24 }}
      key={JSON.stringify(config)}
    >
      {configKeys.map(({ key, label }) => (
        <Form.Item key={key} name={key} label={t(label)}>
          <Input size="large" />
        </Form.Item>
      ))}

      <Divider orientation="left">{t('Registration Settings')}</Divider>

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
