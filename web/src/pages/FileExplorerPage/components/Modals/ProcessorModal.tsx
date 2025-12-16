import React from 'react';
import { Modal, Form, Select, Input, Checkbox } from 'antd';
import { useI18n } from '../../../../i18n';
import type { VfsEntry } from '../../../../api/client';
import type { ProcessorTypeMeta } from '../../../../api/processors';
import { ProcessorConfigForm } from '../../../../components/ProcessorConfigForm';

interface ProcessorModalProps {
  entry: VfsEntry | null;
  visible: boolean;
  loading: boolean;
  processorTypes: ProcessorTypeMeta[];
  selectedProcessor: string;
  config: any;
  savingPath: string;
  overwrite: boolean;
  onOk: () => void;
  onCancel: () => void;
  onSelectedProcessorChange: (type: string) => void;
  onConfigChange: (key: string, value: any) => void;
  onSavingPathChange: (path: string) => void;
  onOverwriteChange: (overwrite: boolean) => void;
}

export const ProcessorModal: React.FC<ProcessorModalProps> = (props) => {
  const {
    entry, visible, loading, processorTypes, selectedProcessor, config,
    savingPath, overwrite, onOk, onCancel, onSelectedProcessorChange,
    onConfigChange, onSavingPathChange, onOverwriteChange
  } = props;
  const [form] = Form.useForm();
  const { t } = useI18n();

  const availableProcessors = React.useMemo(() => {
    if (!entry) return processorTypes;
    if (entry.is_dir) {
      return processorTypes.filter(pt => !!pt.supports_directory);
    }
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    return processorTypes.filter(pt => {
      const exts = pt.supported_exts;
      if (!Array.isArray(exts) || exts.length === 0) return true;
      return exts.includes(ext);
    });
  }, [entry, processorTypes]);

  const selectedProcessorMeta = processorTypes.find(pt => pt.type === selectedProcessor);

  // Sync form when modal opens or selected processor changes
  React.useEffect(() => {
    if (visible) {
      form.setFieldsValue({
        processor_type: selectedProcessor,
        config: config,
      });
    }
  }, [visible, selectedProcessor, config, form]);

  const handleFormValuesChange = (changedValues: any) => {
    if (changedValues.config) {
      for (const key in changedValues.config) {
        onConfigChange(key, changedValues.config[key]);
      }
    }
  };

  return (
    <Modal
      title={t('Process file with processor') + (entry ? `: ${entry.name}` : '')}
      open={visible}
      onCancel={onCancel}
      onOk={onOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onValuesChange={handleFormValuesChange}>
        <Form.Item name="processor_type" label={t('Processor')} required>
          <Select
            onChange={onSelectedProcessorChange}
            options={availableProcessors.map(pt => ({ value: pt.type, label: pt.name }))}
            placeholder={t('Select a processor')}
          />
        </Form.Item>
        <ProcessorConfigForm
          processorMeta={selectedProcessorMeta}
          form={form}
          configPath={['config']}
        />
        {selectedProcessorMeta?.produces_file && (
          <>
            <Form.Item>
              <Checkbox checked={overwrite} onChange={e => onOverwriteChange(e.target.checked)}>
                {t('Overwrite original file')}
              </Checkbox>
            </Form.Item>
            {!overwrite && (
              <Form.Item label={t('Save as new file')}>
                <Input
                  value={savingPath}
                  onChange={e => onSavingPathChange(e.target.value)}
                  placeholder={t('e.g. /newfile.jpg, leave blank to only return result')}
                />
              </Form.Item>
            )}
          </>
        )}
      </Form>
    </Modal>
  );
};
