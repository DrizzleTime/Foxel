import { Card, type CardProps } from 'antd';
import { memo } from 'react';

const PageCard = memo((props: CardProps) => {
    const bodyStyles = (props.styles as { body?: React.CSSProperties } | undefined)?.body;

    return (
      <Card
        {...props}
        style={{ height: '100%', display: 'flex', flexDirection: 'column', ...(props.style || {}) }}
        styles={{
          body: {
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            ...(bodyStyles || {}),
          },
        } as any}
      />
    );
});

export default PageCard;
