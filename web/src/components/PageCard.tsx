import { Card, type CardProps } from 'antd';
import { memo } from 'react';

const PageCard = memo((props: CardProps) => {
    return <Card styles={{ body: { overflowY: 'auto', height: 'calc(100vh - 145px)' } }} {...props} />;
});

export default PageCard;