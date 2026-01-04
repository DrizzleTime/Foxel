# Foxel 插件开发指南

本文档介绍如何开发 Foxel 插件（.foxpkg）。

## 概述

Foxel 插件系统允许第三方开发者扩展系统功能。一个完整的插件可以包含：

- **前端组件**：使用 React + Antd 开发的 UI 界面
- **后端路由**：FastAPI 路由提供 API 服务
- **后端处理器**：文件处理器用于自动化任务

## 插件包结构

```
my-plugin.foxpkg (ZIP 格式)
├── manifest.json           # 插件元数据 (必需)
├── frontend/
│   └── index.js            # 编译后的前端 bundle (可选)
├── backend/
│   ├── routes/             # 后端路由模块 (可选)
│   │   └── api.py
│   └── processors/         # 后端处理器模块 (可选)
│       └── my_processor.py
└── assets/                 # 静态资源 (可选)
    └── icon.svg
```

## manifest.json

```json
{
  "foxpkg": "1.0",
  "key": "my-plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件描述",
  "author": "作者名",
  "website": "https://example.com",
  "license": "MIT",

  "frontend": {
    "entry": "frontend/index.js",
    "openApp": true,
    "supportedExts": ["mp4", "mkv"],
    "defaultBounds": { "width": 800, "height": 600 },
    "defaultMaximized": false,
    "icon": "assets/icon.svg"
  },

  "backend": {
    "routes": [
      {
        "module": "backend/routes/api.py",
        "prefix": "/api/plugins/my-plugin",
        "tags": ["my-plugin"]
      }
    ],
    "processors": [
      {
        "module": "backend/processors/my_processor.py",
        "type": "my_processor",
        "name": "我的处理器"
      }
    ]
  },

  "dependencies": {
    "python": ">=3.10",
    "packages": ["httpx>=0.24"]
  }
}
```

### manifest 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| foxpkg | string | 是 | 格式版本，当前为 "1.0" |
| key | string | 是 | 插件唯一标识，只能包含字母、数字、下划线和连字符 |
| name | string | 是 | 插件显示名称 |
| version | string | 否 | 版本号 |
| description | string | 否 | 插件描述 |
| author | string | 否 | 作者 |
| website | string | 否 | 网站链接 |
| license | string | 否 | 许可证 |
| frontend | object | 否 | 前端配置 |
| backend | object | 否 | 后端配置 |
| dependencies | object | 否 | 依赖配置 |

## 前端开发

### 依赖注入

宿主应用通过 `window.__FOXEL_EXTERNALS__` 暴露共享依赖：

```typescript
const { React, ReactDOM, antd, AntdIcons, foxelApi } = window.__FOXEL_EXTERNALS__;
```

可用的依赖：

- `React` - React 库
- `ReactDOM` - ReactDOM 库
- `antd` - Ant Design 组件库
- `AntdIcons` - Ant Design 图标
- `foxelApi` - Foxel API 封装

### 插件注册

```typescript
window.FoxelRegister({
  // 文件打开模式（必需）
  mount: (container, ctx) => {
    // ctx 包含: filePath, entry, urls, host
    const root = ReactDOM.createRoot(container);
    root.render(<MyComponent {...ctx} />);
    return () => root.unmount(); // 返回清理函数
  },

  // 独立应用模式（可选）
  mountApp: (container, ctx) => {
    // ctx 包含: host
    const root = ReactDOM.createRoot(container);
    root.render(<MyApp host={ctx.host} />);
    return () => root.unmount();
  },
});
```

### 上下文对象

#### 文件打开模式 (mount)

```typescript
interface PluginContext {
  filePath: string;           // 文件路径
  entry: VfsEntry;            // 文件信息
  urls: {
    downloadUrl: string;      // 临时下载链接
    streamUrl: string;        // 流式播放链接
  };
  host: HostApi;
}
```

#### 宿主 API

```typescript
interface HostApi {
  close: () => void;                    // 关闭窗口
  showMessage: (type, content) => void; // 显示消息
  callApi: (path, options) => Promise;  // 调用 API
  getTempLink: (path) => Promise<string>; // 获取临时链接
  getStreamUrl: (path) => string;       // 获取流式 URL
}
```

### 使用 TypeScript 开发

推荐使用 TypeScript + Vite 开发，配置 external：

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    lib: {
      entry: 'src/index.tsx',
      formats: ['iife'],
      name: 'MyPlugin',
      fileName: () => 'index.js',
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'antd', '@ant-design/icons'],
      output: {
        globals: {
          react: 'window.__FOXEL_EXTERNALS__.React',
          'react-dom': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          antd: 'window.__FOXEL_EXTERNALS__.antd',
          '@ant-design/icons': 'window.__FOXEL_EXTERNALS__.AntdIcons',
        },
      },
    },
  },
});
```

## 后端开发

### 路由模块

```python
# backend/routes/api.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/items")
async def list_items():
    return {"code": 0, "data": []}

@router.get("/items/{item_id}")
async def get_item(item_id: str):
    return {"code": 0, "data": {"id": item_id}}
```

**注意**：
- 必须定义名为 `router` 的 APIRouter 实例
- 路由前缀在 manifest 中配置
- 可以使用 `from domain.auth.service import get_current_active_user` 进行认证

### 处理器模块

```python
# backend/processors/my_processor.py
from typing import Any, Dict

class MyProcessor:
    name = "我的处理器"
    supported_exts = ["txt", "md"]
    config_schema = [
        {
            "key": "option1",
            "label": "选项1",
            "type": "string",
            "required": False,
        },
    ]
    produces_file = False
    supports_directory = False
    requires_input_bytes = True

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]):
        # 处理逻辑
        return {"ok": True, "path": path}

# 注册信息
PROCESSOR_TYPE = "my_processor"
PROCESSOR_NAME = MyProcessor.name
CONFIG_SCHEMA = MyProcessor.config_schema
PROCESSOR_FACTORY = lambda: MyProcessor()
```

## 打包

```bash
cd my-plugin
zip -r ../my-plugin.foxpkg . -x "*.DS_Store" -x "__pycache__/*"
```

## 安装

1. 在 Foxel 管理界面进入"插件"页面
2. 点击"安装插件"
3. 上传 `.foxpkg` 文件
4. 等待安装完成

## 调试

- 前端：使用浏览器开发者工具
- 后端：查看应用日志

## 示例

参考 `plugins/video-library/` 目录中的视频库插件示例。

