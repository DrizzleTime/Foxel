import { Form, Input, Button } from 'antd';
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

  return (
    <Form
      layout="vertical"
      initialValues={{
        ...Object.fromEntries(configKeys.map(({ key, default: def }) => [key, config[key] ?? def ?? ''])),
      }}
      onFinish={onSave}
      style={{ marginTop: 24 }}
      key={JSON.stringify(config)}
    >
      {configKeys.map(({ key, label }) => (
        <Form.Item key={key} name={key} label={t(label)}>
          <Input size="large" />
        </Form.Item>
      ))}
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>
          {t('Save')}
        </Button>
      </Form.Item>
    </Form>
  );
}
