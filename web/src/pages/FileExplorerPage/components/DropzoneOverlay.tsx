import { memo } from 'react';
import { theme } from 'antd';

interface DropzoneOverlayProps {
  visible: boolean;
}

export const DropzoneOverlay = memo(function DropzoneOverlay({ visible }: DropzoneOverlayProps) {
  const { token } = theme.useToken();

  if (!visible) {
    return null;
  }

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        borderColor: token.colorPrimary,
        borderStyle: 'dashed',
        borderWidth: 4,
        borderRadius: token.borderRadius,
      }}
    >
      <div style={{ color: 'white', fontSize: 24, fontWeight: 'bold' }}>
        将文件拖放到此处以上传
      </div>
    </div>
  );
});