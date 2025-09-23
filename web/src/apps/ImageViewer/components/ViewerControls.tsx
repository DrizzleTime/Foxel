import React from 'react';
import { Button, Tooltip } from 'antd';
import {
  LeftOutlined,
  RightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  RotateRightOutlined,
  ReloadOutlined,
  CompressOutlined,
} from '@ant-design/icons';

interface ViewerControlsProps {
  style: React.CSSProperties;
  onPrev: () => void;
  onNext: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onRotate: () => void;
  onReset: () => void;
  onFit: () => void;
  disableSwitch: boolean;
}

export const ViewerControls: React.FC<ViewerControlsProps> = ({
  style,
  onPrev,
  onNext,
  onZoomIn,
  onZoomOut,
  onRotate,
  onReset,
  onFit,
  disableSwitch,
}) => (
  <div style={style}>
    <Tooltip title="上一张">
      <Button
        shape="circle"
        type="text"
        icon={<LeftOutlined />}
        onClick={onPrev}
        disabled={disableSwitch}
        style={{ color: '#fff' }}
      />
    </Tooltip>
    <Tooltip title="缩小">
      <Button shape="circle" type="text" icon={<ZoomOutOutlined />} onClick={onZoomOut} style={{ color: '#fff' }} />
    </Tooltip>
    <Tooltip title="放大">
      <Button shape="circle" type="text" icon={<ZoomInOutlined />} onClick={onZoomIn} style={{ color: '#fff' }} />
    </Tooltip>
    <Tooltip title="旋转 90°">
      <Button shape="circle" type="text" icon={<RotateRightOutlined />} onClick={onRotate} style={{ color: '#fff' }} />
    </Tooltip>
    <Tooltip title="重置">
      <Button shape="circle" type="text" icon={<ReloadOutlined />} onClick={onReset} style={{ color: '#fff' }} />
    </Tooltip>
    <Tooltip title="适应窗口">
      <Button shape="circle" type="text" icon={<CompressOutlined />} onClick={onFit} style={{ color: '#fff' }} />
    </Tooltip>
    <Tooltip title="下一张">
      <Button
        shape="circle"
        type="text"
        icon={<RightOutlined />}
        onClick={onNext}
        disabled={disableSwitch}
        style={{ color: '#fff' }}
      />
    </Tooltip>
  </div>
);
