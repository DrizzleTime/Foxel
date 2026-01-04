#!/bin/bash
# 插件打包脚本
# 用法: ./build.sh <plugin-name>  打包单个插件
#       ./build.sh all            打包全部插件

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/dist"

# 打包单个插件的函数
build_plugin() {
    local PLUGIN_NAME="$1"
    local PLUGIN_DIR="${SCRIPT_DIR}/${PLUGIN_NAME}"

    if [ ! -d "${PLUGIN_DIR}" ]; then
        echo "错误: 插件目录不存在: ${PLUGIN_DIR}"
        return 1
    fi

    if [ ! -f "${PLUGIN_DIR}/manifest.json" ]; then
        echo "错误: ${PLUGIN_NAME}/manifest.json 不存在"
        return 1
    fi

    # 检查是否是 TypeScript 项目（存在 package.json 和 src 目录）
    if [ -f "${PLUGIN_DIR}/package.json" ] && [ -d "${PLUGIN_DIR}/src" ]; then
        echo "🔨 构建 ${PLUGIN_NAME} (TypeScript)..."
        cd "${PLUGIN_DIR}"
        
        # 检查是否安装了依赖
        if [ ! -d "node_modules" ]; then
            echo "📦 安装依赖..."
            if command -v bun &> /dev/null; then
                bun install
            else
                npm install
            fi
        fi
        
        # 构建项目
        if command -v bun &> /dev/null; then
            bun run build
        else
            npm run build
        fi
        
        # 检查构建输出
        if [ ! -f "frontend/index.js" ]; then
            echo "❌ 构建失败: 未生成 frontend/index.js"
            return 1
        fi
        echo "✅ 构建完成"
    fi

    local OUTPUT_FILE="${OUTPUT_DIR}/${PLUGIN_NAME}.foxpkg"

    # 删除旧的打包文件
    rm -f "${OUTPUT_FILE}"

    # 打包（排除开发文件）
    cd "${PLUGIN_DIR}"
    zip -r "${OUTPUT_FILE}" . \
        -x "*.DS_Store" \
        -x "__pycache__/*" \
        -x "*.pyc" \
        -x "node_modules/*" \
        -x "src/*" \
        -x "tsconfig.json" \
        -x "vite.config.ts" \
        -x "bun.lock" \
        -x "package-lock.json" \
        -x ".gitignore" \
        -x "build.sh" \
        -x "README.md" \
        -x "CHANGELOG.md"

    echo "✓ ${PLUGIN_NAME}: $(du -h "${OUTPUT_FILE}" | cut -f1)"
}

# 获取所有插件目录
get_all_plugins() {
    for dir in "${SCRIPT_DIR}"/*/; do
        if [ -f "${dir}/manifest.json" ]; then
            basename "${dir}"
        fi
    done
}

mkdir -p "${OUTPUT_DIR}"

if [ "$1" = "all" ] || [ -z "$1" ]; then
    echo "打包全部插件..."
    echo "===================="
    
    PLUGINS=$(get_all_plugins)
    COUNT=0
    FAILED=0
    
    # 临时禁用 set -e，避免单个插件失败导致整个脚本退出
    set +e
    
    for plugin in $PLUGINS; do
        echo ""
        if build_plugin "$plugin"; then
            ((COUNT++))
        else
            echo "❌ ${plugin} 打包失败 (退出码: $?)"
            ((FAILED++))
        fi
    done
    
    # 恢复 set -e
    set -e
    
    echo ""
    echo "===================="
    echo "完成! 成功打包 ${COUNT} 个插件"
    if [ $FAILED -gt 0 ]; then
        echo "失败: ${FAILED} 个插件"
    fi
else
    build_plugin "$1"
    echo "打包完成: ${OUTPUT_DIR}/$1.foxpkg"
fi
