#!/bin/bash
# 插件打包脚本
# 用法: ./build.sh <plugin-name>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="${1:-video-library}"
PLUGIN_DIR="${SCRIPT_DIR}/${PLUGIN_NAME}"
OUTPUT_DIR="${SCRIPT_DIR}/dist"

if [ ! -d "${PLUGIN_DIR}" ]; then
    echo "错误: 插件目录不存在: ${PLUGIN_DIR}"
    exit 1
fi

if [ ! -f "${PLUGIN_DIR}/manifest.json" ]; then
    echo "错误: manifest.json 不存在"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

cd "${PLUGIN_DIR}"
OUTPUT_FILE="${OUTPUT_DIR}/${PLUGIN_NAME}.foxpkg"

# 删除旧的打包文件
rm -f "${OUTPUT_FILE}"

# 打包
zip -r "${OUTPUT_FILE}" . -x "*.DS_Store" -x "__pycache__/*" -x "*.pyc" -x "node_modules/*"

echo "打包完成: ${OUTPUT_FILE}"
echo "文件大小: $(du -h "${OUTPUT_FILE}" | cut -f1)"

