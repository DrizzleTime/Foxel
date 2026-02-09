import React from 'react';
import { Form, Input, Select, Typography } from 'antd';
import type { ProcessorTypeMeta } from '../api/processors';
import { useI18n } from '../i18n';

interface ProcessorConfigFormProps {
  processorMeta: ProcessorTypeMeta | undefined;
  form: any;
  configPath: string[]; 
}

export const ProcessorConfigForm: React.FC<ProcessorConfigFormProps> = ({ processorMeta, configPath }) => {
  const { t } = useI18n();
  if (!processorMeta) {
    return <Typography.Text type="secondary">{t('Please select a processor')}</Typography.Text>;
  }
  if (!processorMeta.config_schema?.length) {
    return <Typography.Text type="secondary">{t('No config fields')}</Typography.Text>;
  }

  return (
    <>
      {processorMeta.config_schema.map(field => {
        const rules = field.required ? [{ required: true, message: t('Please input {label}', { label: field.label }) }] : [];
        let inputNode: React.ReactNode;

        switch (field.type) {
          case 'password':
            inputNode = <Input.Password placeholder={field.placeholder} />;
            break;
          case 'number':
            inputNode = <Input type="number" placeholder={field.placeholder} />;
            break;
          case 'select':
            inputNode = (
              <Select placeholder={field.placeholder || t('Please select')}>
                {field.options?.map((opt: any) => (
                  <Select.Option key={String(opt.value)} value={opt.value}>
                    {opt.label}
                  </Select.Option>
                ))}
              </Select>
            );
            break;
          default:
            inputNode = <Input placeholder={field.placeholder} />;
        }

        return (
          <Form.Item
            key={field.key}
            name={[...configPath, field.key]}
            label={t(field.label)}
            rules={rules}
            initialValue={field.default}
          >
            {inputNode}
          </Form.Item>
        );
      })}
    </>
  );
};
