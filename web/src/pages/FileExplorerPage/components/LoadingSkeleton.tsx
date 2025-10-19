import type { FC } from 'react';
import { Skeleton, theme } from 'antd';

type LoadingMode = 'grid' | 'list';

interface LoadingSkeletonProps {
  mode: LoadingMode;
  count?: number;
}

const createArray = (length: number) => Array.from({ length }, (_, index) => index);

export const LoadingSkeleton: FC<LoadingSkeletonProps> = ({ mode, count }) => {
  const { token } = theme.useToken();
  const fallbackCount = mode === 'grid' ? 50 : 30;
  const items = createArray(count ?? fallbackCount);

  if (mode === 'grid') {
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 16,
          padding: 16,
        }}
      >
        {items.map((key) => (
          <div
            key={key}
            style={{
              background: token.colorBgElevated,
              borderRadius: token.borderRadius,
              padding: 16,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <Skeleton.Button active block style={{ height: 96, borderRadius: token.borderRadiusLG }} />
            <Skeleton active title={false} paragraph={{ rows: 2, width: ['80%', '60%'] }} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ padding: '0 16px' }}>
      {items.map((key) => (
        <div
          key={key}
          style={{
            display: 'grid',
            gridTemplateColumns: '48px 1fr',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Skeleton.Avatar active shape="square" size={32} />
          <div style={{ paddingLeft: 16 }}>
            <Skeleton active title={false} paragraph={{ rows: 1, width: '60%' }} />
            <Skeleton active title={false} paragraph={{ rows: 1, width: '40%' }} />
          </div>
        </div>
      ))}
    </div>
  );
};

