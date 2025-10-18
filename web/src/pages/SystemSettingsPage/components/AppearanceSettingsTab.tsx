import { Form, Input, Button, InputNumber, Card, Radio, message } from 'antd';
import { useTheme } from '../../../contexts/ThemeContext';
import { useI18n } from '../../../i18n';

interface ThemeKeyMap {
  MODE: string;
  PRIMARY: string;
  RADIUS: string;
  TOKENS: string;
  CSS: string;
}

interface AppearanceSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
  themeKeys: ThemeKeyMap;
}

export default function AppearanceSettingsTab({
  config,
  loading,
  onSave,
  themeKeys,
}: AppearanceSettingsTabProps) {
  const { previewTheme } = useTheme();
  const { t } = useI18n();

  return (
    <Form
      layout="vertical"
      initialValues={{
        [themeKeys.MODE]: config[themeKeys.MODE] ?? 'light',
        [themeKeys.PRIMARY]: config[themeKeys.PRIMARY] ?? '#111111',
        [themeKeys.RADIUS]: Number(config[themeKeys.RADIUS] ?? '10'),
        [themeKeys.TOKENS]: config[themeKeys.TOKENS] ?? '',
        [themeKeys.CSS]: config[themeKeys.CSS] ?? '',
      }}
      onValuesChange={(_, all) => {
        try {
          const tokens = all[themeKeys.TOKENS] ? JSON.parse(all[themeKeys.TOKENS]) : undefined;
          previewTheme({
            mode: all[themeKeys.MODE],
            primaryColor: all[themeKeys.PRIMARY],
            borderRadius: typeof all[themeKeys.RADIUS] === 'number' ? all[themeKeys.RADIUS] : undefined,
            customTokens: tokens,
            customCSS: all[themeKeys.CSS],
          });
        } catch {
          previewTheme({
            mode: all[themeKeys.MODE],
            primaryColor: all[themeKeys.PRIMARY],
            borderRadius: typeof all[themeKeys.RADIUS] === 'number' ? all[themeKeys.RADIUS] : undefined,
            customCSS: all[themeKeys.CSS],
          });
        }
      }}
      onFinish={async (vals) => {
        if (vals[themeKeys.TOKENS]) {
          try {
            JSON.parse(String(vals[themeKeys.TOKENS]));
          } catch {
            message.error(t('Advanced tokens must be valid JSON'));
            return;
          }
        }
        await onSave(vals);
      }}
      style={{ marginTop: 24 }}
      key={'appearance-' + JSON.stringify(config)}
    >
      <Card title={t('Theme')}>
        <Form.Item name={themeKeys.MODE} label={t('Theme Mode')}>
          <Radio.Group buttonStyle="solid">
            <Radio.Button value="light">{t('Light')}</Radio.Button>
            <Radio.Button value="dark">{t('Dark')}</Radio.Button>
            <Radio.Button value="system">{t('Follow System')}</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Form.Item name={themeKeys.PRIMARY} label={t('Primary Color')}>
          <Input type="color" size="large" />
        </Form.Item>
        <Form.Item name={themeKeys.RADIUS} label={t('Border Radius')}>
          <InputNumber min={0} max={24} style={{ width: '100%' }} />
        </Form.Item>
      </Card>
      <Card title={t('Advanced')} style={{ marginTop: 24 }}>
        <Form.Item name={themeKeys.TOKENS} label={t('Override AntD Tokens (JSON)')} tooltip={t('e.g. {"colorText": "#222"}')}>
          <Input.TextArea autoSize={{ minRows: 4 }} placeholder='{ "colorText": "#222" }' />
        </Form.Item>
        <Form.Item name={themeKeys.CSS} label={t('Custom CSS')}>
          <Input.TextArea autoSize={{ minRows: 6 }} placeholder={":root{ }\n/* CSS */"} />
        </Form.Item>
      </Card>
      <Form.Item style={{ marginTop: 24 }}>
        <Button type="primary" htmlType="submit" loading={loading} block>
          {t('Save')}
        </Button>
      </Form.Item>
    </Form>
  );
}
