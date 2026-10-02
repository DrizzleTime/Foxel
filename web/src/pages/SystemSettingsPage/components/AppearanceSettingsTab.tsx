import { Form, Input, Button, InputNumber, ColorPicker, Radio, message } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { useEffect } from 'react';
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
  onSave: (values: Record<string, unknown>) => Promise<boolean>;
  themeKeys: ThemeKeyMap;
}

export default function AppearanceSettingsTab({
  config,
  loading,
  onSave,
  themeKeys,
}: AppearanceSettingsTabProps) {
  const { previewTheme, refreshTheme } = useTheme();
  const { t } = useI18n();

  useEffect(() => () => { void refreshTheme(); }, [refreshTheme]);

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
      className="fx-appearance-form"
      key={'appearance-' + JSON.stringify(config)}
    >
      <section className="fx-settings-section">
        <h3>{t('Theme')}</h3>
        <Form.Item name={themeKeys.MODE} label={t('Theme Mode')}>
          <Radio.Group buttonStyle="solid">
            <Radio.Button value="light">{t('Light')}</Radio.Button>
            <Radio.Button value="dark">{t('Dark')}</Radio.Button>
            <Radio.Button value="system">{t('Follow System')}</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name={themeKeys.PRIMARY}
          label={t('Primary Color')}
          getValueFromEvent={(_, hex: string) => hex}
        >
          <ColorPicker showText disabledAlpha />
        </Form.Item>
        <Form.Item name={themeKeys.RADIUS} label={t('Border Radius')}>
          <InputNumber min={0} max={24} style={{ width: 120 }} />
        </Form.Item>
      </section>
      <section className="fx-settings-section">
        <h3>{t('Advanced')}</h3>
        <Form.Item name={themeKeys.TOKENS} label={t('Override AntD Tokens (JSON)')} tooltip={t('e.g. {"colorText": "#222"}')}>
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} placeholder='{ "colorText": "#222" }' />
        </Form.Item>
        <Form.Item name={themeKeys.CSS} label={t('Custom CSS')}>
          <Input.TextArea autoSize={{ minRows: 4, maxRows: 10 }} placeholder={":root{ }\n/* CSS */"} />
        </Form.Item>
      </section>
      <Form.Item className="fx-settings-save">
        <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
          {t('Save')}
        </Button>
      </Form.Item>
    </Form>
  );
}
