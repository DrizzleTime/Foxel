#!/bin/bash
# 文本编辑器插件构建脚本

set -e

echo "🚀 开始构建文本编辑器插件..."

# 检查依赖
if ! command -v bun &> /dev/null; then
    echo "❌ 未找到 bun，请先安装 bun"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
bun install

# 清理旧文件
echo "🧹 清理旧文件..."
bun run clean

# 构建
echo "🔨 编译 TypeScript..."
bun run build

# 检查输出文件
if [ ! -f "frontend/index.js" ]; then
    echo "❌ 构建失败：未生成 frontend/index.js"
    exit 1
fi

echo "✅ 构建完成！"
echo "📦 输出文件：frontend/index.js"
ls -lh frontend/index.js

