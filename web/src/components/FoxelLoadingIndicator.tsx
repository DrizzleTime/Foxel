import type { CSSProperties } from 'react';

interface FoxelLoadingIndicatorProps {
  className?: string;
  style?: CSSProperties;
}

export default function FoxelLoadingIndicator({ className, style }: FoxelLoadingIndicatorProps) {
  return (
    <span
      className={['fx-loading-indicator', className].filter(Boolean).join(' ')}
      style={style}
      aria-hidden="true"
    >
      <span className="fx-loading-indicator-mark" />
    </span>
  );
}
