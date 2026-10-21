import React from 'react';
import { Modal, Form, Select, Input, Checkbox } from 'antd';
import { useI18n } from '../../../../i18n';
import type { VfsEntry } from '../../../../api/client';
import { processorSupportsEntry, type ProcessorTypeMeta } from '../../../../api/processors';
import { ProcessorConfigForm } from '../../../../components/ProcessorConfigForm';

interface ProcessorModalProps {
  entries: VfsEntry[];
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
    entries, visible, loading, processorTypes, selectedProcessor, config,
    savingPath, overwrite, onOk, onCancel, onSelectedProcessorChange,
    onConfigChange, onSavingPathChange, onOverwriteChange
  } = props;
  const [form] = Form.useForm();
  const { t } = useI18n();

  const availableProcessors = React.useMemo(() => {
    return processorTypes.filter(pt => entries.every(entry => processorSupportsEntry(pt, entry)));
  }, [entries, processorTypes]);

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
      title={t('Process file with processor') + (entries.length > 1
        ? `: ${t('Selected {n} items', { n: entries.length })}`
        : entries[0] ? `: ${entries[0].name}` : '')}
      open={visible}
      onCancel={onCancel}
      onOk={onOk}
      confirmLoading={loading}
      closable={!loading}
      maskClosable={!loading}
      keyboard={!loading}
      cancelButtonProps={{ disabled: loading }}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onValuesChange={handleFormValuesChange}>
        {entries.length > 1 && (
          <div style={{ maxHeight: 160, overflow: 'auto', marginBottom: 16 }}>
            {entries.map(entry => <div key={entry.name}>{entry.name}</div>)}
          </div>
        )}
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
              <Form.Item label={entries.length > 1 ? t('Output directory') : t('Save as new file')}>
                <Input
                  value={savingPath}
                  onChange={e => onSavingPathChange(e.target.value)}
                  placeholder={entries.length > 1
                    ? t('Save each file to this directory; leave blank to only return results')
                    : t('e.g. /newfile.jpg, leave blank to only return result')}
                />
              </Form.Item>
            )}
          </>
        )}
      </Form>
    </Modal>
  );
};
