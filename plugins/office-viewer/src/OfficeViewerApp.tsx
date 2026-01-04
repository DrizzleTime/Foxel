/**
 * Office 文档查看器主组件
 */
import React, { useState, useEffect } from 'react';
import { Spin, Result, Button } from 'antd';
import type { PluginContext } from './foxel-types';

export const OfficeViewerApp: React.FC<PluginContext> = ({ filePath, host }) => {
  const { foxelApi } = window.__FOXEL_EXTERNALS__;
  
  const [url, setUrl] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(undefined);
    setUrl(undefined);

    const cleaned = filePath.replace(/^\/+/, '');
    foxelApi.vfs
      .getTempLinkToken(cleaned)
      .then(res => {
        if (cancelled) return;
        // 获取系统状态中的 file_domain
        const fileDomain = window.__FOXEL_SYSTEM_STATUS__?.file_domain;
        const baseUrl = fileDomain || window.location.origin;
        const fullUrl = new URL(res.url, baseUrl).href;
        const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fullUrl)}`;
        setUrl(officeUrl);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setErr(e.message || '加载文档链接失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filePath, foxelApi]);

  if (loading) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin tip="正在准备文档..." />
      </div>
    );
  }

  if (err) {
    return (
      <Result
        status="error"
        title="无法加载文档"
        subTitle={err}
        extra={
          <Button type="primary" onClick={host.close}>
            关闭
          </Button>
        }
      />
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        background: 'var(--ant-color-bg-container, #fff)',
      }}
    >
      {url ? (
        <iframe
          src={url}
          width="100%"
          height="100%"
          style={{ border: 'none' }}
          title="Office Document Viewer"
        />
      ) : (
        <Result
          status="warning"
          title="文档链接无效"
          subTitle="未能成功生成文档的在线查看链接。"
          extra={
            <Button type="primary" onClick={host.close}>
              关闭
            </Button>
          }
        />
      )}
    </div>
  );
};

