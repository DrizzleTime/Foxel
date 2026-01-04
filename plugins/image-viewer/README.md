# Foxel 图片查看器插件

内置图片查看器，支持常见图片与部分 RAW 格式预览，包含 EXIF 信息和直方图显示。

## 开发环境要求

- Node.js 18+
- Bun (推荐) 或 npm

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

构建后会在 `frontend/` 目录生成 `index.js` 文件。

### 项目结构

```
image-viewer/
├── src/
│   ├── components/          # React 组件
│   │   ├── ImageViewerApp.tsx  # 主应用组件
│   │   ├── HistogramPlot.tsx   # 直方图组件
│   │   ├── InfoPanel.tsx       # 信息面板
│   │   ├── Filmstrip.tsx       # 胶片带
│   │   ├── ViewerControls.tsx  # 控制按钮
│   │   ├── InfoRows.tsx        # 信息行
│   │   └── SectionTitle.tsx    # 章节标题
│   ├── utils.ts             # 工具函数
│   ├── styles.ts            # 样式定义
│   ├── foxel-types.d.ts     # 类型定义
│   └── index.tsx            # 入口文件
├── frontend/
│   └── index.js             # 构建输出（自动生成）
├── assets/
│   └── icon.svg             # 插件图标
├── manifest.json            # 插件配置
├── package.json             # 项目配置
├── tsconfig.json            # TypeScript 配置
├── vite.config.ts           # Vite 构建配置
└── build.sh                 # 构建脚本

```

## 技术栈

- **TypeScript** - 类型安全
- **React 18** - UI 框架
- **Ant Design** - 组件库
- **Vite** - 构建工具

## 外部依赖

以下依赖由宿主应用提供，构建时会自动排除：

- react
- react-dom
- antd
- @ant-design/icons

## 功能特性

- ✅ 支持常见图片格式（PNG、JPG、GIF、WebP、SVG 等）
- ✅ 支持 RAW 格式（ARW、CR2、CR3、NEF、RW2、ORF、PEF、DNG）
- ✅ EXIF 信息展示
- ✅ RGB 直方图
- ✅ 主色调自适应背景
- ✅ 图片缩放、旋转、拖拽
- ✅ 胶片带快速切换
- ✅ 键盘快捷键支持

## 快捷键

- `←/→` - 上一张/下一张
- `Ctrl/Cmd + +` - 放大
- `Ctrl/Cmd + -` - 缩小
- 鼠标滚轮 - 缩放
- 双击 - 快速缩放
- 拖拽 - 移动图片

## 打包

构建完成后，可以使用项目根目录的打包脚本生成 `.foxpkg` 文件：

```bash
cd ../../
./plugins/build.sh
```

生成的插件包位于 `plugins/dist/image-viewer.foxpkg`。

