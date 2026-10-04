import { Form, Input, Button, InputNumber, ColorPicker, Segmented, Slider, Collapse, Tooltip, Tag, message } from 'antd';
import { BgColorsOutlined, CheckOutlined, FileTextOutlined, FolderOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons';
import { useEffect } from 'react';
import type { CSSProperties } from 'react';
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

const accentColors = ['#111111', '#d8584a', '#3778dc', '#35956c', '#ca9b13', '#8660c9', '#607085'];

function AccentColorControl({ value = '#111111', onChange }: { value?: string; onChange?: (value: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="fx-appearance-colors">
      {accentColors.map((color) => (
        <Tooltip key={color} title={color}>
          <button
            type="button"
            className="fx-appearance-swatch"
            style={{ '--swatch-color': color } as CSSProperties}
            aria-label={color}
            aria-pressed={value.toLowerCase() === color}
            onClick={() => onChange?.(color)}
          >
            {value.toLowerCase() === color && <CheckOutlined />}
          </button>
        </Tooltip>
      ))}
      <ColorPicker value={value} onChange={(_, hex) => onChange?.(hex)} disabledAlpha>
        <Button type="text" icon={<BgColorsOutlined />} title={t('Custom Color')} aria-label={t('Custom Color')} />
      </ColorPicker>
    </div>
  );
}

function RadiusControl({ value = 10, onChange }: { value?: number; onChange?: (value: number) => void }) {
  const { t } = useI18n();
  return (
    <div className="fx-appearance-radius">
      <Slider min={0} max={24} value={value} onChange={onChange} aria-label={t('Border Radius')} />
      <InputNumber min={0} max={24} value={value} onChange={(next) => { if (next !== null) onChange?.(next); }} suffix="px" aria-label={t('Border Radius')} />
    </div>
  );
}

export default function AppearanceSettingsTab({
  config,
  loading,
  onSave,
  themeKeys,
}: AppearanceSettingsTabProps) {
  const { previewTheme, refreshTheme } = useTheme();
  const { t } = useI18n();
  const [form] = Form.useForm();

  useEffect(() => () => { void refreshTheme(); }, [refreshTheme]);

  const applyPreview = (values: Record<string, unknown>) => {
    const radius = values[themeKeys.RADIUS];
    let tokens;
    try {
      tokens = values[themeKeys.TOKENS] ? JSON.parse(String(values[themeKeys.TOKENS])) : undefined;
    } catch {
      // Keep the preview usable while the user is editing JSON.
    }
    previewTheme({
      mode: values[themeKeys.MODE] as 'light' | 'dark' | 'system',
      primaryColor: String(values[themeKeys.PRIMARY]),
      borderRadius: typeof radius === 'number' ? radius : undefined,
      customTokens: tokens,
      customCSS: String(values[themeKeys.CSS] ?? ''),
    });
  };

  const restoreDefaults = () => {
    const values = {
      [themeKeys.MODE]: 'light',
      [themeKeys.PRIMARY]: '#111111',
      [themeKeys.RADIUS]: 10,
      [themeKeys.TOKENS]: '',
      [themeKeys.CSS]: '',
    };
    form.setFieldsValue(values);
    applyPreview(values);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{
        [themeKeys.MODE]: config[themeKeys.MODE] ?? 'light',
        [themeKeys.PRIMARY]: config[themeKeys.PRIMARY] ?? '#111111',
        [themeKeys.RADIUS]: Number(config[themeKeys.RADIUS] ?? '10'),
        [themeKeys.TOKENS]: config[themeKeys.TOKENS] ?? '',
        [themeKeys.CSS]: config[themeKeys.CSS] ?? '',
      }}
      onValuesChange={(_, all) => applyPreview(all)}
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
      <section className="fx-appearance-options">
        <Form.Item className="fx-settings-row" name={themeKeys.MODE} label={t('Theme Mode')}>
          <Segmented options={[
            { value: 'system', label: t('Follow System') },
            { value: 'light', label: t('Light') },
            { value: 'dark', label: t('Dark') },
          ]} />
        </Form.Item>
        <Form.Item
          name={themeKeys.PRIMARY}
          label={t('Primary Color')}
          className="fx-settings-row"
        >
          <AccentColorControl />
        </Form.Item>
        <Form.Item className="fx-settings-row" name={themeKeys.RADIUS} label={t('Border Radius')}>
          <RadiusControl />
        </Form.Item>
      </section>
      <section className="fx-appearance-preview">
        <h3>{t('Live Preview')}</h3>
        <div className="fx-appearance-preview-surface">
          <div className="fx-appearance-preview-toolbar">
            <span><FolderOutlined /> {t('File Manager')}</span>
            <Tag color="default">Foxel</Tag>
          </div>
          <div className="fx-appearance-preview-file">
            <FileTextOutlined />
            <span>README.md</span>
            <Tag color="processing">Markdown</Tag>
          </div>
          <div className="fx-appearance-preview-actions">
            <Button>{t('Cancel')}</Button>
            <Button type="primary" icon={<CheckOutlined />}>{t('Confirm')}</Button>
          </div>
        </div>
      </section>
      <Collapse
        ghost
        className="fx-appearance-advanced"
        items={[{
          key: 'advanced',
          label: t('Advanced'),
          forceRender: true,
          children: <>
            <Form.Item name={themeKeys.TOKENS} label={t('Override AntD Tokens (JSON)')} tooltip={t('e.g. {"colorText": "#222"}')}>
              <Input.TextArea className="fx-settings-code" autoSize={{ minRows: 3, maxRows: 8 }} placeholder='{ "colorText": "#222" }' />
            </Form.Item>
            <Form.Item name={themeKeys.CSS} label={t('Custom CSS')}>
              <Input.TextArea className="fx-settings-code" autoSize={{ minRows: 4, maxRows: 10 }} placeholder={":root{ }\n/* CSS */"} />
            </Form.Item>
          </>,
        }]}
      />
      <Form.Item className="fx-settings-save">
        <div className="fx-settings-actions">
          <Button type="text" onClick={restoreDefaults} disabled={loading} icon={<UndoOutlined />}>{t('Restore Defaults')}</Button>
          <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>{t('Save')}</Button>
        </div>
      </Form.Item>
    </Form>
  );
}
