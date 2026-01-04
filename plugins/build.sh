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

    local OUTPUT_FILE="${OUTPUT_DIR}/${PLUGIN_NAME}.foxpkg"

    # 删除旧的打包文件
    rm -f "${OUTPUT_FILE}"

    # 打包
    cd "${PLUGIN_DIR}"
    zip -r "${OUTPUT_FILE}" . -x "*.DS_Store" -x "__pycache__/*" -x "*.pyc" -x "node_modules/*"

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
    
    for plugin in $PLUGINS; do
        build_plugin "$plugin"
        ((COUNT++))
    done
    
    echo "===================="
    echo "完成! 共打包 ${COUNT} 个插件"
else
    build_plugin "$1"
    echo "打包完成: ${OUTPUT_DIR}/$1.foxpkg"
fi
