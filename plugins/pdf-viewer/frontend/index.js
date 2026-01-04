/**
 * PDF 查看器插件前端入口
 */
(function () {
  'use strict';

  const externals = window.__FOXEL_EXTERNALS__;
  if (!externals) {
    console.error('[pdf-viewer] Foxel externals not found');
    return;
  }

  const { React, ReactDOM, antd, foxelApi } = externals;
  const { useState, useEffect } = React;
  const { Spin, Result, Button } = antd;

  function PdfViewerApp({ filePath, entry, urls, host }) {
    const [url, setUrl] = useState();
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState();

    useEffect(() => {
      let cancelled = false;
      setLoading(true);
      setErr(undefined);
      setUrl(undefined);

      const cleaned = filePath.replace(/^\/+/, '');
      foxelApi.vfs.getTempLinkToken(cleaned)
        .then(res => {
          if (cancelled) return;
          const publicUrl = foxelApi.vfs.getTempPublicUrl(res.token);
          setUrl(publicUrl + '#toolbar=1&navpanes=1');
        })
        .catch(e => {
          if (!cancelled) setErr(e.message || '获取临时链接失败');
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });

      return () => { cancelled = true; };
    }, [filePath]);

    if (loading) {
      return React.createElement('div', {
        style: { width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }
      }, React.createElement(Spin, { tip: '正在加载 PDF...' }));
    }

    if (err) {
      return React.createElement(Result, {
        status: 'error',
        title: '无法加载 PDF',
        subTitle: err,
        extra: React.createElement(Button, { type: 'primary', onClick: host.close }, '关闭')
      });
    }

    if (!url) {
      return React.createElement(Result, {
        status: 'warning',
        title: '无可用链接',
        subTitle: '未能生成 PDF 的临时访问链接',
        extra: React.createElement(Button, { type: 'primary', onClick: host.close }, '关闭')
      });
    }

    return React.createElement('div', {
      style: { width: '100%', height: '100%', background: 'var(--ant-color-bg-container, #fff)' }
    },
      React.createElement('iframe', {
        src: url,
        width: '100%',
        height: '100%',
        title: 'PDF Viewer',
        style: { border: 'none' }
      })
    );
  }

  // 注册插件
  window.FoxelRegister({
    mount: (container, ctx) => {
      const root = ReactDOM.createRoot(container);
      root.render(React.createElement(PdfViewerApp, ctx));
      return () => root.unmount();
    },
  });
})();

