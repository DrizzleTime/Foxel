import React, { useEffect, useState } from 'react';
import { Input, Modal } from 'antd';
import { useI18n } from '../../../../i18n';

interface CreateFileModalProps {
  open: boolean;
  onOk: (name: string) => void;
  onCancel: () => void;
}

export const CreateFileModal: React.FC<CreateFileModalProps> = ({ open, onOk, onCancel }) => {
  const [name, setName] = useState('');
  const { t } = useI18n();

  useEffect(() => {
    if (open) {
      setName('');
    }
  }, [open]);

  const handleOk = () => {
    onOk(name);
  };

  return (
    <Modal
      title={t('New File')}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okButtonProps={{ disabled: !name.trim() }}
      destroyOnHidden
    >
      <Input
        placeholder={t('Filename')}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onPressEnter={handleOk}
        autoFocus
      />
    </Modal>
  );
};
