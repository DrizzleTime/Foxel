import { useEffect, useState } from 'react';
import { Form, Input, Modal, message } from 'antd';
import { vfsApi, type VfsEntry } from '../../../../api/client';
import { useI18n } from '../../../../i18n';

interface CompressModalProps {
  entries: VfsEntry[];
  path: string;
  /** Optional full-path sources (batch mode). When set, entries are ignored as sources. */
  sources?: string[] | null;
  onDone: () => void;
  onCancel: () => void;
}

export function CompressModal({ entries, path, sources, onDone, onCancel }: CompressModalProps) {
  const { t } = useI18n();
  const [form] = Form.useForm<{ dst: string }>();
  const [busy, setBusy] = useState(false);
  const hasSources = !!sources && sources.length > 0;

  useEffect(() => {
    if (hasSources) {
      form.setFieldsValue({ dst: `${path === '/' ? '' : path}/archive.zip` });
    } else if (entries.length) {
      const name = entries.length === 1 ? entries[0].name : 'archive';
      form.setFieldsValue({ dst: `${path === '/' ? '' : path}/${name}.zip` });
    }
  }, [entries, path, form, hasSources]);

  const submit = async () => {
    if (busy) return;
    try {
      const { dst } = await form.validateFields();
      setBusy(true);
      const resolvedSources = hasSources
        ? sources!
        : entries.map(entry => `${path === '/' ? '' : path}/${entry.name}`);
      const result = await vfsApi.compress(resolvedSources, dst.trim());
      if (result.task_id) {
        message.info(t('Compression task queued. View progress in Task Queue.'));
      } else {
        message.success(t(result.queued ? 'Compression submitted to storage. Refresh the folder after it finishes.' : 'Archive created'));
      }
      onDone();
    } catch (error) {
      if (error instanceof Error) message.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t('Compress to ZIP')}
      open={entries.length > 0 || hasSources}
      onOk={submit}
      onCancel={onCancel}
      confirmLoading={busy}
      closable={!busy}
      maskClosable={!busy}
      keyboard={!busy}
      cancelButtonProps={{ disabled: busy }}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="dst"
          label={t('Archive path')}
          rules={[
            { required: true, whitespace: true, message: t('Please enter an archive path') },
            { pattern: /\.zip\s*$/i, message: t('Archive name must end with .zip') },
          ]}
        >
          <Input disabled={busy} onPressEnter={submit} autoFocus />
        </Form.Item>
      </Form>
    </Modal>
  );
}
