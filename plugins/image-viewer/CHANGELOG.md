# 更新日志

## v1.0.0 - TypeScript 重构版本 (2026-01-04)

### 🎉 重大改进

- **TypeScript 支持**：完全使用 TypeScript/TSX 重写，提供完整的类型安全
- **现代化构建系统**：使用 Vite 作为构建工具，构建速度更快
- **模块化架构**：代码拆分为多个组件和模块，提高可维护性
- **外部依赖优化**：正确排除宿主提供的 React、ReactDOM、Ant Design 依赖

### 📦 构建优化

- 打包后大小：**31.45 KB** (gzip: 12.05 KB)
- 单文件输出：所有代码打包成单个 `index.js` 文件
- 生产环境优化：使用 esbuild 压缩

### 🛠️ 开发体验

- 完整的类型定义文件 (`foxel-types.d.ts`)
- 支持热更新开发模式 (`bun run dev`)
- 清晰的项目结构和组件拆分
- 详细的 README 文档

### 📁 项目结构

```
src/
├── components/          # React 组件
│   ├── ImageViewerApp.tsx
│   ├── HistogramPlot.tsx
│   ├── InfoPanel.tsx
│   ├── Filmstrip.tsx
│   ├── ViewerControls.tsx
│   ├── InfoRows.tsx
│   └── SectionTitle.tsx
├── utils.ts            # 工具函数
├── styles.ts           # 样式定义
├── foxel-types.d.ts    # 类型定义
└── index.tsx           # 入口文件
```

### 🔧 构建命令

```bash
# 安装依赖
bun install

# 开发模式
bun run dev

# 构建生产版本
bun run build

# 或使用构建脚本
./build.sh
```

### ✨ 功能保持不变

- ✅ 支持常见图片格式和 RAW 格式
- ✅ EXIF 信息展示
- ✅ RGB 直方图
- ✅ 主色调自适应背景
- ✅ 图片缩放、旋转、拖拽
- ✅ 胶片带快速切换
- ✅ 键盘快捷键支持

### 🔄 迁移说明

原 JavaScript 版本的 `frontend/index.js` 已被 TypeScript 构建版本替代。
如需查看原始代码，请从 git 历史中获取。

