import React, { useMemo, useState } from 'react';
import { Card, Input, Tag, Typography, message } from 'antd';
import { PlayCircleOutlined, SearchOutlined } from '@ant-design/icons';
import type { AppOpenComponentProps } from '../types';

type MockVideoItem = {
  id: string;
  title: string;
  year: number;
  duration: string;
  tags: string[];
};

const MOCK_VIDEOS: MockVideoItem[] = [
  { id: '1', title: '流浪地球 3（预告）', year: 2025, duration: '00:02:12', tags: ['科幻', '预告'] },
  { id: '2', title: '赛博雨夜', year: 2024, duration: '01:32:10', tags: ['悬疑', '都市'] },
  { id: '3', title: '夏日回声', year: 2023, duration: '01:18:45', tags: ['剧情', '治愈'] },
  { id: '4', title: '荒原追迹', year: 2022, duration: '01:45:02', tags: ['动作', '冒险'] },
  { id: '5', title: '月海电台', year: 2021, duration: '00:49:30', tags: ['纪录片'] },
  { id: '6', title: '时空备忘录', year: 2020, duration: '02:05:11', tags: ['科幻', '爱情'] },
];

export const VideoLibraryApp: React.FC<AppOpenComponentProps> = () => {
  const [q, setQ] = useState('');

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return MOCK_VIDEOS;
    return MOCK_VIDEOS.filter(v =>
      v.title.toLowerCase().includes(s)
      || v.tags.some(tag => tag.toLowerCase().includes(s)),
    );
  }, [q]);

  return (
    <div style={{ padding: 12, height: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          影视库
        </Typography.Title>
        <div style={{ flex: 1 }} />
        <Input
          allowClear
          value={q}
          onChange={(e) => setQ(e.target.value)}
          prefix={<SearchOutlined />}
          placeholder="搜索影片/标签"
          style={{ maxWidth: 320 }}
        />
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
          {filtered.map(v => (
            <Card
              key={v.id}
              hoverable
              size="small"
              styles={{ body: { padding: 10 } } as any}
              cover={(
                <div
                  style={{
                    height: 120,
                    background: 'linear-gradient(135deg, #0b1020 0%, #22314a 60%, #2b3b5c 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'rgba(255,255,255,0.92)',
                  }}
                >
                  <PlayCircleOutlined style={{ fontSize: 44 }} />
                </div>
              )}
              onClick={() => message.info('演示数据：暂未接入真实文件')}
            >
              <Typography.Text strong ellipsis style={{ display: 'block' }}>
                {v.title}
              </Typography.Text>
              <div style={{ marginTop: 6, display: 'flex', gap: 8, color: 'var(--ant-color-text-tertiary)', fontSize: 12 }}>
                <span>{v.year}</span>
                <span>·</span>
                <span>{v.duration}</span>
              </div>
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {v.tags.map(tag => (
                  <Tag key={tag} style={{ marginInlineEnd: 0 }}>
                    {tag}
                  </Tag>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};
