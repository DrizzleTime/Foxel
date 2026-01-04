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
  "key": "com.example.myplugin",
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
| key | string | 是 | 插件唯一标识，命名空间格式（如 com.example.plugin），每个部分以小写字母开头，只能包含小写字母和数字，至少两级 |
| name | string | 是 | 插件显示名称 |
| version | string | 否 | 版本号 |
| description | string | 否 | 插件描述 |
| author | string | 否 | 作者 |
| website | string | 否 | 网站链接 |
| license | string | 否 | 许可证 |
| frontend | object | 否 | 前端配置 |
| backend | object | 否 | 后端配置 |
| dependencies | object | 否 | 依赖配置 |

### 插件命名规范（重要）

插件 `key` 必须遵循 **Java 命名空间格式**，类似于域名反向表示法：

#### ✅ 有效的命名示例

- `com.example.myplugin` - 推荐格式
- `io.github.username.viewer` - GitHub 项目
- `cc.foxel.imageeditor` - 组织项目
- `cn.mycompany.tools.converter` - 多级命名空间

#### ❌ 无效的命名示例

- `my-plugin` - 缺少命名空间
- `MyPlugin` - 包含大写字母
- `com.example.my-plugin` - 包含连字符
- `com.example.My_Plugin` - 包含大写字母和下划线
- `example` - 只有一级

#### 命名规则详解

1. **命名空间层级**: 至少 2 级，推荐 3 级（如 `com.company.plugin`）
2. **字符限制**: 只能使用小写字母（a-z）和数字（0-9）
3. **分隔符**: 使用点号（`.`）分隔各级
4. **开头字符**: 每一级必须以小写字母开头
5. **长度建议**: 总长度建议不超过 64 字符

#### 推荐的命名空间前缀

| 前缀 | 用途 | 示例 |
|------|------|------|
| `com.yourcompany.*` | 公司/商业项目 | `com.acme.viewer` |
| `io.github.username.*` | GitHub 个人项目 | `io.github.john.editor` |
| `org.projectname.*` | 开源组织项目 | `org.apache.plugin` |
| `cn.yourname.*` | 中国个人/公司 | `cn.zhangsan.tools` |
| `dev.yourname.*` | 开发者个人项目 | `dev.alice.converter` |

#### 正则表达式

```regex
^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$
```

**解释**:
- `^[a-z][a-z0-9]*` - 第一级：小写字母开头，后跟小写字母或数字
- `(\.[a-z][a-z0-9]*)+` - 后续级别：点号 + 小写字母开头 + 小写字母或数字，至少一个

## 前端开发

### 技术栈

- **React 19** - 现代化的 React 框架
- **Ant Design 6** - 企业级 UI 组件库
- **TypeScript** - 类型安全的开发体验
- **Vite 7** - 快速的构建工具

### 依赖注入

宿主应用通过 `window.__FOXEL_EXTERNALS__` 暴露共享依赖：

```typescript
const { React, ReactDOM, antd, AntdIcons, foxelApi } = window.__FOXEL_EXTERNALS__;
```

可用的依赖：

- `React` - React 19.2.3
- `ReactDOM` - ReactDOM 19.2.3（包含 `createRoot` 等 API）
- `antd` - Ant Design 6
- `AntdIcons` - Ant Design Icons 6
- `foxelApi` - Foxel API 封装
  - `request` - HTTP 请求函数
  - `vfs` - 虚拟文件系统 API
  - `plugins` - 插件管理 API
  - `baseUrl` - API 基础 URL

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

推荐使用 TypeScript + Vite 开发，以下是完整的配置：

#### package.json

```json
{
  "name": "foxel-plugin-myplugin",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "clean": "rm -rf dist frontend/index.js"
  },
  "devDependencies": {
    "@ant-design/icons": "6",
    "@types/node": "^22.10.5",
    "@types/react": "^19.2.7",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^5.1.2",
    "antd": "6",
    "react": "^19.2.3",
    "react-dom": "^19.2.3",
    "typescript": "~5.9.3",
    "vite": "^7.3.0"
  }
}
```

**重要**: 确保依赖版本与宿主应用保持一致（React 19, Ant Design 6）。

#### vite.config.ts

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  
  // 🔑 关键: 替换 Node.js 环境变量
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/index.tsx'),
      formats: ['iife'],
      name: 'MyPlugin',
      fileName: () => 'index.js',
    },
    outDir: 'frontend',
    emptyOutDir: false,
    
    rollupOptions: {
      // 🔑 关键: 排除宿主提供的依赖
      // 注意必须包含 'react-dom/client'
      external: ['react', 'react-dom', 'react-dom/client', 'antd', '@ant-design/icons'],
      output: {
        // 映射到全局变量
        globals: {
          'react': 'window.__FOXEL_EXTERNALS__.React',
          'react-dom': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'react-dom/client': 'window.__FOXEL_EXTERNALS__.ReactDOM',
          'antd': 'window.__FOXEL_EXTERNALS__.antd',
          '@ant-design/icons': 'window.__FOXEL_EXTERNALS__.AntdIcons',
        },
        format: 'iife',
        extend: false,
      },
    },
    
    cssCodeSplit: false,
    minify: 'esbuild',
    sourcemap: false,
  },
});
```

#### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

#### 类型定义文件 (src/foxel-types.d.ts)

```typescript
/**
 * Foxel 插件类型定义
 */

declare global {
  interface Window {
    __FOXEL_EXTERNALS__: {
      React: typeof import('react');
      ReactDOM: typeof import('react-dom/client');
      antd: typeof import('antd');
      AntdIcons: typeof import('@ant-design/icons');
      foxelApi: FoxelApi;
    };
    FoxelRegister: (plugin: PluginRegistration) => void;
  }
}

export interface VfsEntry {
  name: string;
  is_dir: boolean;
  size?: number;
  mtime?: number;
  path?: string;
}

export interface HostApi {
  close: () => void;
  showMessage: (type: 'success' | 'error' | 'info' | 'warning', content: string) => void;
  callApi: <T = unknown>(path: string, options?: RequestInit) => Promise<T>;
  getTempLink?: (filePath: string) => Promise<string>;
  getStreamUrl?: (filePath: string) => string;
}

export interface PluginContext {
  filePath: string;
  entry: VfsEntry;
  urls: {
    downloadUrl: string;
    streamUrl: string;
  };
  host: HostApi;
}

export interface PluginRegistration {
  mount?: (container: HTMLElement, ctx: PluginContext) => (() => void) | void;
  mountApp?: (container: HTMLElement, ctx: { host: HostApi }) => (() => void) | void;
}

export interface FoxelApi {
  baseUrl: string;
  request: (path: string, options?: RequestInit) => Promise<any>;
  vfs: {
    getTempLinkToken: (path: string) => Promise<{ token: string; url: string }>;
    getTempPublicUrl: (token: string) => string;
    readFile: (path: string) => Promise<string | ArrayBuffer>;
    uploadFile: (path: string, content: Blob) => Promise<void>;
    stat: (path: string) => Promise<VfsEntry>;
  };
  plugins: {
    call: (pluginKey: string, method: string, args: any[]) => Promise<any>;
  };
}
```

#### 插件入口 (src/index.tsx)

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import type { PluginContext } from './foxel-types';
import MyComponent from './MyComponent';

// 确保外部依赖已加载
const externals = window.__FOXEL_EXTERNALS__;
if (!externals) {
  console.error('[com.example.myplugin] Foxel externals not found');
  throw new Error('Foxel externals not found');
}

// 注册插件
window.FoxelRegister({
  mount: (container: HTMLElement, ctx: PluginContext) => {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(MyComponent, ctx));
    return () => root.unmount();
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

## 构建与打包

### 构建前端

```bash
cd com.example.myplugin  # 使用你的插件命名空间作为目录名
bun install  # 或 npm install
bun run build
```

构建成功后，会在 `frontend/index.js` 生成编译后的文件。

### 构建验证

在打包前，验证构建产物是否正确：

```bash
# 检查是否有 process.env 引用（应该为 0）
grep -c "process\.env" frontend/index.js || echo "0"

# 检查是否有 React 内部代码泄漏（应该无输出）
grep -i "reactcurrentowner\|__secret" frontend/index.js

# 检查 IIFE 调用是否正确
tail -c 250 frontend/index.js
# 应该看到: })(window.__FOXEL_EXTERNALS__.React,...)
```

### 打包

使用构建脚本或手动打包：

```bash
# 方式 1: 使用 build.sh (如果有)
./build.sh com.example.myplugin

# 方式 2: 手动打包
cd com.example.myplugin
zip -r ../com.example.myplugin.foxpkg \
  manifest.json \
  frontend/ \
  backend/ \
  assets/ \
  package.json \
  -x "*.DS_Store" \
  -x "*/__pycache__/*" \
  -x "*/node_modules/*" \
  -x "*/src/*" \
  -x "*.ts" \
  -x "*.tsx"
```

**注意**: 
- 只打包必要文件（manifest.json, frontend/, backend/, assets/, package.json）
- 不要打包源代码、node_modules、缓存文件等

## 安装

1. 在 Foxel 管理界面进入"插件"页面
2. 点击"安装插件"
3. 上传 `.foxpkg` 文件
4. 等待安装完成

## 调试

### 前端调试

1. **开发模式**:
   ```bash
   cd my-plugin
   bun run dev
   ```

2. **使用浏览器开发者工具**:
   - Console: 查看日志和错误
   - Network: 检查 API 请求
   - React DevTools: 检查组件状态

3. **验证 externals**:
   ```javascript
   // 在浏览器控制台
   console.log(window.__FOXEL_EXTERNALS__);
   console.log(window.__FOXEL_EXTERNALS__.React);
   console.log(window.__FOXEL_EXTERNALS__.ReactDOM.createRoot);
   ```

### 后端调试

- 查看应用日志
- 使用 FastAPI 的交互式文档（Swagger UI）

## 常见问题

### 1. 插件加载失败：`process is not defined`

**原因**: 构建时 `process.env.NODE_ENV` 没有被替换。

**解决方案**: 在 `vite.config.ts` 中添加：
```typescript
define: {
  'process.env.NODE_ENV': JSON.stringify('production'),
}
```

### 2. 插件加载失败：`Cannot read properties of undefined (reading 'ReactCurrentOwner')`

**原因**: `react-dom/client` 没有被正确排除为外部依赖。

**解决方案**: 在 `vite.config.ts` 的 `external` 中添加 `'react-dom/client'`：
```typescript
external: ['react', 'react-dom', 'react-dom/client', 'antd', '@ant-design/icons']
```

并在 `globals` 中映射：
```typescript
globals: {
  'react-dom/client': 'window.__FOXEL_EXTERNALS__.ReactDOM',
}
```

### 3. 依赖版本不匹配

**原因**: 插件使用的 React/Ant Design 版本与宿主不一致。

**解决方案**: 确保 package.json 中的版本与宿主一致：
- React: `^19.2.3`
- React DOM: `^19.2.3`
- Ant Design: `6`
- @ant-design/icons: `6`

### 4. 构建产物过大

**原因**: 外部依赖没有被正确排除。

**检查方法**:
```bash
# 查看构建日志中的模块数量
bun run build
# 应该只有 15-20 个模块

# 检查文件大小
ls -lh frontend/index.js
# 应该在 10-30 KB 之间（取决于插件复杂度）
```

### 5. TypeScript 类型错误

**解决方案**: 确保安装了正确版本的类型定义：
```bash
bun add -d @types/react@^19.2.7 @types/react-dom@^19.2.3
```

## 最佳实践

### 1. 性能优化

- **懒加载大型组件**:
  ```typescript
  const HeavyComponent = React.lazy(() => import('./HeavyComponent'));
  
  function MyComponent() {
    return (
      <Suspense fallback={<Spin />}>
        <HeavyComponent />
      </Suspense>
    );
  }
  ```

- **避免打包不必要的依赖**: 确保 external 配置正确

### 2. 错误处理

```typescript
function MyComponent({ filePath, host }: PluginContext) {
  const [error, setError] = useState<string>();
  
  useEffect(() => {
    loadData().catch(err => {
      setError(err.message);
      host.showMessage('error', '加载失败');
    });
  }, []);
  
  if (error) {
    return <Alert type="error" message={error} />;
  }
  
  return <div>...</div>;
}
```

### 3. 使用 VFS API

```typescript
const { foxelApi } = window.__FOXEL_EXTERNALS__;

// 获取临时链接
const { token } = await foxelApi.vfs.getTempLinkToken(filePath);
const url = foxelApi.vfs.getTempPublicUrl(token);

// 读取文件
const content = await foxelApi.vfs.readFile(filePath);

// 上传文件
await foxelApi.vfs.uploadFile(filePath, blob);
```

### 4. 响应式设计

```typescript
import { useMediaQuery } from 'react';

function MyComponent() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  
  return (
    <Layout style={{ padding: isMobile ? 8 : 24 }}>
      {/* ... */}
    </Layout>
  );
}
```

## 示例插件

参考以下内置插件的实现：

- `plugins/image-viewer/` - 图片查看器（EXIF 解析、直方图）
- `plugins/text-editor/` - 文本编辑器（Monaco Editor, Markdown）
- `plugins/video-library/` - 视频库（前后端集成示例）
- `plugins/pdf-viewer/` - PDF 查看器（iframe 嵌入）
- `plugins/office-viewer/` - Office 文档查看器（第三方服务集成）

## 相关文档

- [React 19 文档](https://react.dev/)
- [Ant Design 6 文档](https://ant.design/)
- [Vite 文档](https://vitejs.dev/)
- [TypeScript 文档](https://www.typescriptlang.org/)

## 获取帮助

- 查看 `plugins/VITE_CONFIG_FIX.md` - Vite 配置问题
- 查看 `plugins/EXTERNAL_DEPENDENCY_FIX.md` - 外部依赖问题
- 查看 `plugins/REACT_19_UPGRADE.md` - React 19 升级指南

