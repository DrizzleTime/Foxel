# Foxel 文本编辑器插件

内置文本/代码编辑器，支持常见文本与代码格式，Markdown 实时预览。

## ⚠️ 重要更新

**v1.1.0** - 编辑器组件现在由插件自己提供，不再依赖宿主注入。

### 变更说明

- ✅ **自包含编辑器**: 插件内置 Monaco Editor 和 Markdown Editor
- ✅ **独立依赖管理**: 编辑器库由插件自己安装和维护
- ✅ **更大的灵活性**: 可以自由选择编辑器版本和配置
- ⚠️ **包体积增加**: 从 18 KB 增加到 1.1 MB（包含编辑器）

## 开发环境要求

- Node.js 18+
- Bun (推荐) 或 npm

## 依赖说明

### 宿主提供的依赖（external）
- `react` - React 框架
- `react-dom` - React DOM
- `antd` - Ant Design UI 库

### 插件自己的依赖（bundled）
- `@monaco-editor/react` ^4.6.0 - Monaco 代码编辑器
- `@uiw/react-md-editor` ^4.0.4 - Markdown 编辑器

## 开发指南

### 安装依赖

```bash
bun install
```

### 开发模式

```bash
bun run dev
```

### 构建生产版本

```bash
# 使用构建脚本
chmod +x build.sh
./build.sh

# 或者直接使用 bun
bun run build
```

构建后会在 `frontend/` 目录生成：
- `index.js` - 主 JavaScript 文件（~1.1 MB）
- `foxel-plugin-text-editor.css` - 样式文件（~34 KB）

## 项目结构

```
text-editor/
├── src/
│   ├── TextEditorApp.tsx    # 主应用组件
│   ├── utils.ts             # 工具函数（语言映射）
│   ├── foxel-types.d.ts     # 类型定义
│   └── index.tsx            # 入口文件
├── frontend/
│   ├── index.js             # 构建输出（自动生成）
│   └── foxel-plugin-text-editor.css  # 样式文件（自动生成）
├── assets/
│   └── icon.svg             # 插件图标
├── package.json             # 项目配置
├── tsconfig.json            # TypeScript 配置
├── vite.config.ts           # Vite 构建配置
├── build.sh                 # 构建脚本
└── manifest.json            # 插件配置
```

## 功能特性

### 代码编辑器（Monaco Editor）
- ✅ 语法高亮（支持 50+ 种语言）
- ✅ 代码自动补全
- ✅ 代码折叠
- ✅ 查找替换
- ✅ 多光标编辑
- ✅ 自动换行

### Markdown 编辑器
- ✅ 实时预览
- ✅ 分屏编辑
- ✅ Markdown 语法支持
- ✅ 代码块高亮
- ✅ 表格支持

### 支持的文件格式

**Web 技术**
- JavaScript/JSX, TypeScript/TSX
- HTML, CSS, SCSS, SASS, LESS
- Vue

**数据格式**
- JSON, YAML, XML, TOML, INI

**编程语言**
- Python, Java, C/C++, PHP, Ruby, Go, Rust
- Swift, Kotlin, Scala, C#, F#, Perl, R, Lua, Dart

**数据库**
- SQL

**脚本**
- Shell (bash, zsh, fish), PowerShell, Batch

**构建工具**
- Dockerfile, Makefile, Gradle, CMake

**文档**
- Markdown

## 快捷键

- `Ctrl/Cmd + S` - 保存文件
- Monaco Editor 内置快捷键（查找、替换等）

## 构建配置

### Vite 配置要点

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      // 只排除宿主提供的依赖
      external: ['react', 'react-dom', 'antd'],
      // 编辑器库会被打包进插件
    },
  },
});
```

### 懒加载优化

编辑器组件使用 React.lazy 进行懒加载：

```typescript
const MonacoEditor = lazy(() => import('@monaco-editor/react'));
const MDEditor = lazy(() => import('@uiw/react-md-editor'));
```

这样可以：
- 减少初始加载时间
- 按需加载编辑器
- 提升用户体验

## 性能考虑

### 文件大小限制
- 小于 1MB 的文件：完整加载和编辑
- 大于 1MB 的文件：仅预览前 1MB，禁用编辑和保存

### 构建优化
- esbuild 压缩（gzip 后约 383 KB）
- CSS 提取到单独文件
- Monaco Editor 按需加载语言支持

## 打包

构建完成后，可以使用项目根目录的打包脚本生成 `.foxpkg` 文件：

```bash
cd ../../
./plugins/build.sh text-editor
```

生成的插件包位于 `plugins/dist/text-editor.foxpkg`（约 420 KB）。

## 版本历史

### v1.1.0 (2026-01-04)
- ✨ 编辑器组件改为插件自己提供
- ✨ 使用 @monaco-editor/react 和 @uiw/react-md-editor
- ✨ 懒加载优化
- ⚠️ 包体积增加（权衡：更大的灵活性）

### v1.0.0
- ✅ 初始版本
- ✅ 依赖宿主提供的编辑器组件

