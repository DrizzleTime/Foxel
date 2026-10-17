import { useEffect, useState } from 'react';
import { Form, Input, Modal, Typography, message } from 'antd';
import { vfsApi, type VfsEntry } from '../../../../api/client';
import { useI18n } from '../../../../i18n';

interface ExtractModalProps {
  entry: VfsEntry | null;
  path: string;
  onDone: () => void;
  onCancel: () => void;
}

export function ExtractModal({ entry, path, onDone, onCancel }: ExtractModalProps) {
  const { t } = useI18n();
  const [form] = Form.useForm<{ dst: string }>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (entry) {
      const name = entry.name.replace(/\.zip$/i, '') || 'archive';
      form.setFieldsValue({ dst: `${path === '/' ? '' : path}/${name}` });
    }
  }, [entry, path, form]);

  const submit = async () => {
    if (busy || !entry) return;
    try {
      const { dst } = await form.validateFields();
      setBusy(true);
      await vfsApi.extract(`${path === '/' ? '' : path}/${entry.name}`, dst.trim());
      message.info(t('Extraction task queued. View progress in Task Queue.'));
      onDone();
    } catch (error) {
      if (error instanceof Error) message.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t('Extract ZIP')}
      open={!!entry}
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
          label={t('Destination folder')}
          rules={[{ required: true, whitespace: true, message: t('Please enter a destination folder') }]}
        >
          <Input disabled={busy} onPressEnter={submit} autoFocus />
        </Form.Item>
        <Typography.Text type="secondary">{t('Extract into a new folder. Existing folders cannot be overwritten.')}</Typography.Text>
      </Form>
    </Modal>
  );
}
