import { memo, useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, message, Modal, Typography } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../../api/client';
import { videoRoomsApi, type VideoRoomInfo } from '../../../../api/videoRooms';
import { useSystemStatus } from '../../../../contexts/SystemContext';
import { useI18n } from '../../../../i18n';

interface VideoRoomModalProps {
  entry: VfsEntry | null;
  path: string;
  open: boolean;
  onCancel: () => void;
}

export const VideoRoomModal = memo(function VideoRoomModal({ entry, path, open, onCancel }: VideoRoomModalProps) {
  const [form] = Form.useForm();
  const systemStatus = useSystemStatus();
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [createdRoom, setCreatedRoom] = useState<VideoRoomInfo | null>(null);

  const defaultName = entry?.name || '';
  const roomUrl = useMemo(() => {
    if (!createdRoom) return '';
    const baseUrl = systemStatus?.app_domain || window.location.origin;
    return new URL(`/room/${createdRoom.token}`, baseUrl).href;
  }, [createdRoom, systemStatus?.app_domain]);

  useEffect(() => {
    if (!open) return;
    setCreatedRoom(null);
    form.setFieldsValue({ name: defaultName });
  }, [defaultName, form, open]);

  const handleCreate = async () => {
    if (!entry) return;
    try {
      const values = await form.validateFields();
      setLoading(true);
      const base = path === '/' ? '' : path;
      const fullPath = `${base}/${entry.name}`.replace(/\/{2,}/g, '/');
      const room = await videoRoomsApi.create({
        name: values.name || entry.name,
        path: fullPath,
      });
      setCreatedRoom(room);
      message.success(t('Video room created'));
    } catch (e: any) {
      message.error(e.message || t('Create failed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!roomUrl) return;
    navigator.clipboard.writeText(roomUrl);
    message.success(t('Copied to clipboard'));
  };

  return (
    <Modal
      title={createdRoom ? t('Video room created') : t('Create Video Room')}
      open={open}
      onCancel={onCancel}
      onOk={createdRoom ? onCancel : handleCreate}
      okText={createdRoom ? t('Done') : t('Create')}
      confirmLoading={loading}
      destroyOnHidden
    >
      {createdRoom ? (
        <div>
          <Typography.Paragraph>{t('Share this room link with friends')}</Typography.Paragraph>
          <Form layout="vertical">
            <Form.Item label={t('Video Room Link')}>
              <div style={{ display: 'flex', gap: 8 }}>
                <Input readOnly value={roomUrl} style={{ flex: 1 }} />
                <Button icon={<CopyOutlined />} onClick={handleCopy}>
                  {t('Copy')}
                </Button>
              </div>
            </Form.Item>
          </Form>
        </div>
      ) : (
        <Form form={form} layout="vertical" initialValues={{ name: defaultName }}>
          <Form.Item name="name" label={t('Video Room Name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
});
