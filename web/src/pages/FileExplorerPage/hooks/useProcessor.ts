import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useI18n } from '../../../i18n';
import { processorsApi, processorSupportsEntry, type ProcessorTypeMeta } from '../../../api/processors';
import type { VfsEntry } from '../../../api/client';

interface ProcessorParams {
  path: string;
  processorTypes: ProcessorTypeMeta[];
  refresh: () => void;
}

export function useProcessor({ path, processorTypes, refresh }: ProcessorParams) {
  const { t } = useI18n();
  const [modal, setModal] = useState<{ entries: VfsEntry[]; basePath: string; visible: boolean }>({ entries: [], basePath: path, visible: false });
  const [selectedProcessor, setSelectedProcessor] = useState<string>('');
  const [config, setConfig] = useState<any>({});
  const [savingPath, setSavingPath] = useState('');
  const [overwrite, setOverwrite] = useState(true);
  const [loading, setLoading] = useState(false);

  const handleOk = useCallback(async () => {
    if (loading || !modal.entries.length || !selectedProcessor) return;
    const processor = processorTypes.find(pt => pt.type === selectedProcessor);
    if (!processor || !modal.entries.every(entry => processorSupportsEntry(processor, entry))) return;
    setLoading(true);
    try {
      const schema = processor.config_schema || [];
      const finalConfig: any = {};
      schema.forEach(field => {
        let val = config[field.key];
        if ((field.type as any) === 'object' && typeof val === 'string') {
          try { val = JSON.parse(val); } catch { /* ignore */ }
        }
        if (val === undefined) val = field.default;
        finalConfig[field.key] = val;
      });

      const failedEntries: VfsEntry[] = [];
      const errors: string[] = [];
      const taskIds: string[] = [];
      const multiple = modal.entries.length > 1;
      for (const entry of modal.entries) {
        const outputPath = savingPath
          ? (multiple ? `${savingPath.replace(/\/+$/, '')}/${entry.name}` : savingPath)
          : undefined;
        try {
          const resp = await processorsApi.process({
            path: (modal.basePath === '/' ? '' : modal.basePath) + '/' + entry.name,
            processor_type: selectedProcessor,
            config: finalConfig,
            save_to: processor.produces_file && !overwrite ? outputPath : undefined,
            overwrite: processor.produces_file && overwrite ? true : undefined,
          });
          taskIds.push(resp.task_id);
        } catch (error) {
          failedEntries.push(entry);
          errors.push(`${entry.name}: ${error instanceof Error ? error.message : t('Processing failed')}`);
        }
      }
      if (taskIds.length) {
        message.success(multiple ? `${t('Tasks submitted')}: ${taskIds.length}` : `${t('Task submitted')}: ${taskIds[0]}`);
        if (overwrite || savingPath) refresh();
      }
      if (failedEntries.length) {
        // Keep only unsubmitted files so retries do not duplicate successful tasks.
        if (multiple && failedEntries.length === 1 && savingPath) {
          setSavingPath(`${savingPath.replace(/\/+$/, '')}/${failedEntries[0].name}`);
        }
        setModal({ ...modal, entries: failedEntries });
        message.error(errors.join('; '));
      } else {
        setModal({ entries: [], basePath: modal.basePath, visible: false });
      }
    } catch (e: any) {
      message.error(e.message || t('Processing failed'));
    } finally {
      setLoading(false);
    }
  }, [modal, loading, selectedProcessor, processorTypes, config, overwrite, savingPath, refresh, t]);

  const handleCancel = useCallback(() => {
    if (loading) return;
    setModal(current => ({ ...current, entries: [], visible: false }));
    setSelectedProcessor('');
    setConfig({});
    setSavingPath('');
    setOverwrite(false);
  }, [loading]);

  const handleConfigChange = useCallback((key: string, value: any) => {
    setConfig((c: any) => ({ ...c, [key]: value }));
  }, []);

  const handleProcessorTypeChange = useCallback((type: string) => {
    setSelectedProcessor(type);
    const meta = processorTypes.find(p => p.type === type);
    const newConfig: any = {};
    if (meta?.config_schema) {
      for (const field of meta.config_schema) {
        if (field.default !== undefined) {
          newConfig[field.key] = field.default;
        }
      }
    }
    setConfig(newConfig);
    setOverwrite(!!meta?.produces_file);
  }, [processorTypes]);

  const openModal = useCallback((entries: VfsEntry[], processorType: string) => {
    if (!entries.length) return;
    handleProcessorTypeChange(processorType);
    setModal({ entries: [...entries], basePath: path, visible: true });
    setSavingPath(entries.length > 1 ? '' : (path === '/' ? '' : path) + '/' + entries[0].name);
  }, [path, handleProcessorTypeChange]);

  return {
    processorModal: modal,
    selectedProcessor,
    processorConfig: config,
    processorSavingPath: savingPath,
    processorOverwrite: overwrite,
    processorLoading: loading,
    openProcessorModal: openModal,
    handleProcessorOk: handleOk,
    handleProcessorCancel: handleCancel,
    setSelectedProcessor: handleProcessorTypeChange,
    setProcessorConfig: handleConfigChange,
    setProcessorSavingPath: setSavingPath,
    setProcessorOverwrite: setOverwrite,
  };
}
