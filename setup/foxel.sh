#!/bin/bash

#================================================================================
# Foxel 一键部署与更新脚本
#
# 作者: maxage
# 版本: 1.7 (增加下载镜像, 解决网络问题)
# 描述: 此脚本用于自动化安装、配置和管理 Foxel 项目 (使用 Docker Compose)。
#       - 智能检测现有安装，提供安装向导和管理菜单两种模式。
#       - 自动检测并安装依赖。
#       - 为国内用户提供镜像源切换选项。
#
# 一键运行命令:
# bash <(curl -sL "https://raw.githubusercontent.com/DrizzleTime/Foxel/main/setup/foxel.sh?_=$(date +%s)")
#================================================================================

# --- 消息打印函数 ---
info() {
    echo "[信息] $1"
}

warn() {
    echo "[警告] $1"
}

error() {
    echo "[错误] $1"
}

# --- 基础函数 ---
command_exists() {
    command -v "$1" &> /dev/null
}

confirm_action() {
    local prompt_message="$1"
    printf "%s" "${prompt_message} (y/n): "
    read confirmation
    if [[ "$confirmation" =~ ^[Yy]$ ]]; then
        return 0 # Yes
    else
        return 1 # No
    fi
}

# --- IP地址检测函数 (只输出IP) ---
get_public_ipv4() {
    curl -4 -s --max-time 2 https://api.ipify.org || \
    curl -4 -s --max-time 2 https://ifconfig.me/ip || \
    curl -4 -s --max-time 2 https://icanhazip.com
}

get_public_ipv6() {
    curl -6 -s --max-time 2 https://api64.ipify.org || \
    curl -6 -s --max-time 2 https://ifconfig.co
}

get_private_ip() {
    # 尝试多种方法获取最主要的内网IPv4地址
    ip -4 route get 1.1.1.1 2>/dev/null | awk -F"src " 'NR==1{print $2}' | awk '{print $1}' || \
    hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) {print $i; exit}}' || \
    ip -4 addr 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -n 1
}


# --- 依赖与环境检查 ---
check_and_install_dependencies() {
    info "正在检查所需依赖..."
    declare -A deps=( [curl]="curl" [openssl]="openssl" [ss]="iproute2" )
    local missing_deps=()
    for cmd in "${!deps[@]}"; do
        if ! command_exists "$cmd"; then
            missing_deps+=("${deps[$cmd]}")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        warn "检测到以下依赖项缺失: ${missing_deps[*]}"
        if confirm_action "是否尝试自动安装它们？"; then
            local pm_cmd=""
            if command_exists apt-get; then pm_cmd="sudo apt-get update && sudo apt-get install -y";
            elif command_exists yum; then pm_cmd="sudo yum install -y";
            elif command_exists dnf; then pm_cmd="sudo dnf install -y";
            else error "未检测到 apt, yum 或 dnf。请手动安装: ${missing_deps[*]}"; exit 1; fi
            info "即将使用命令安装: '$pm_cmd ${missing_deps[*]}'"
            $pm_cmd "${missing_deps[@]}"
            for cmd in "${!deps[@]}"; do
                if ! command_exists "$cmd"; then error "依赖 '${deps[$cmd]}' 自动安装失败。"; exit 1; fi
            done
            info "依赖已成功安装。"
        else
            error "用户取消了安装。请先手动安装依赖: ${missing_deps[*]}"; exit 1
        fi
    else
        info "所有基础依赖均已满足。"
    fi
}

initialize_environment() {
    check_and_install_dependencies
    if ! command_exists docker; then
        error "未找到 Docker。请参照官方文档安装: https://docs.docker.com/engine/install/"; exit 1;
    fi
    if ! docker info &> /dev/null; then error "Docker deamon 未在运行。请先启动 Docker。"; exit 1; fi
    info "Docker 环境检测通过。"

    if command_exists docker-compose; then COMPOSE_CMD="docker-compose";
    elif docker compose version &> /dev/null; then COMPOSE_CMD="docker compose";
    else error "未找到 Docker Compose。请安装 Docker Compose v1 或 v2。"; exit 1; fi
    info "检测到 Docker Compose 命令: $COMPOSE_CMD"
}

# --- 新安装流程 ---
install_new_foxel() {
    info "--- 开始 Foxel 全新安装 ---"
    local install_path
    while true; do
        read -p "请输入您想在哪里创建 Foxel 的数据目录 (例如: /opt/docker): " install_path
        if [[ -z "$install_path" ]]; then warn "输入不能为空，请重新输入。"; continue; fi
        if [ ! -d "$install_path" ]; then
            if confirm_action "目录 '$install_path' 不存在。您想现在创建它吗？"; then
                mkdir -p "$install_path"
                if [ $? -eq 0 ]; then info "目录 '$install_path' 创建成功。"; break;
                else error "创建目录 '$install_path' 失败。"; fi
            else info "操作已取消。"; fi
        else info "将使用已存在的目录 '$install_path'。"; break; fi
    done
    echo

    local foxel_dir="$install_path/Foxel"
    info "将在 '$foxel_dir' 目录中创建所需文件..."
    mkdir -p "$foxel_dir/data/"{db,mount} && chmod 777 "$foxel_dir/data/"{db,mount}
    if [ $? -ne 0 ]; then error "创建或设置子目录权限失败。"; exit 1; fi
    cd "$foxel_dir" || exit

    info "正在下载 'compose.yaml'..."
    local COMPOSE_MIRROR_URL="https://ghproxy.com/https://raw.githubusercontent.com/DrizzleTime/Foxel/main/compose.yaml"
    local COMPOSE_OFFICIAL_URL="https://raw.githubusercontent.com/DrizzleTime/Foxel/main/compose.yaml"
    
    if ! curl -L -o compose.yaml "$COMPOSE_MIRROR_URL"; then
        warn "镜像源下载失败，正在尝试从官方源下载..."
        if ! curl -L -o compose.yaml "$COMPOSE_OFFICIAL_URL"; then
            error "下载 'compose.yaml' 失败。请检查您的网络连接。"; exit 1;
        fi
    fi
    info "'compose.yaml' 下载成功。"
    echo

    if confirm_action "您的服务器是否位于中国大陆（以便为您选择更快的镜像源）？"; then
        info "正在切换到国内镜像源..."
        sed -i 's|^\( *\)image: ghcr.io/drizzletime/foxel:latest|\1#image: ghcr.io/drizzletime/foxel:latest|' compose.yaml
        sed -i 's|^\( *\)#image: ghcr.nju.edu.cn/drizzletime/foxel:latest|\1image: ghcr.nju.edu.cn/drizzletime/foxel:latest|' compose.yaml
        info "已成功切换到 ghcr.nju.edu.cn 镜像源。"
    else
        info "将使用默认的 ghcr.io 官方镜像源。"
    fi
    echo

    local new_port
    while true; do
        read -p "请输入新的对外端口 (或直接按回车使用默认的 8088): " new_port
        if [[ -z "$new_port" ]]; then
            new_port="8088"
            info "将使用默认端口 8088。"
            break
        fi

        if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [ "$new_port" -lt 1 ] || [ "$new_port" -gt 65535 ]; then
            warn "输入无效。请输入 1-65535 之间的数字。"
            continue
        fi

        if ss -tuln | grep -q ":${new_port}\b"; then
            warn "端口 $new_port 已被占用，请换一个。"
        else
            sed -i "s/\"8088:80\"/\"$new_port:80\"/" compose.yaml
            info "端口已成功修改为 $new_port。"
            break
        fi
    done
    echo

    if ! confirm_action "是否需要生成新的随机密钥 (推荐)？(选择 'n' 将使用默认值)"; then
        info "将使用 'compose.yaml' 文件中的默认密钥。"
    else
        info "正在生成新的随机密钥..."
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=$(openssl rand -base64 32)|" compose.yaml
        sed -i "s|TEMP_LINK_SECRET_KEY=.*|TEMP_LINK_SECRET_KEY=$(openssl rand -base64 32)|" compose.yaml
        info "新的密钥已成功生成并替换。"
    fi
    echo

    if confirm_action "所有配置已准备就绪！您想现在启动 Foxel 项目吗？"; then
        info "正在启动 Foxel 服务... 这可能需要一些时间来拉取镜像。"
        $COMPOSE_CMD pull && $COMPOSE_CMD up -d
        if [ $? -eq 0 ]; then
            info "Foxel 部署成功！"
            info "-------------------------------------------------"
            info "正在检测服务器IP地址，请稍候..."
            
            # 先捕获所有IP地址
            local public_ipv4=$(get_public_ipv4 2>/dev/null)
            local public_ipv6=$(get_public_ipv6 2>/dev/null)
            local private_ip=$(get_private_ip 2>/dev/null)
            local final_port=$new_port
            local ip_found=false

            echo
            info "部署完成！您可以通过以下地址访问 Foxel:"

            if [[ -n "$private_ip" ]]; then
                echo "  - 局域网地址: http://${private_ip}:${final_port}"
                ip_found=true
            fi
            if [[ -n "$public_ipv4" ]]; then
                echo "  - 公网地址 (IPv4): http://${public_ipv4}:${final_port}"
                ip_found=true
            fi
            if [[ -n "$public_ipv6" ]]; then
                # 正确格式化IPv6地址
                echo "  - 公网地址 (IPv6): http://[${public_ipv6}]:${final_port}"
                ip_found=true
            fi

            if ! $ip_found; then
                warn "未能自动检测到服务器IP地址。"
                echo "  请手动使用 http://[您的服务器IP]:${final_port} 访问它。"
            fi
            echo "-------------------------------------------------"
        else 
            error "启动 Foxel 失败。请运行 'cd $foxel_dir && $COMPOSE_CMD logs' 查看日志。"
        fi
    else 
        info "操作已取消。您可以稍后进入 '$foxel_dir' 并手动运行 '$COMPOSE_CMD up -d'。"
    fi
}

# --- 现有安装管理 ---
get_foxel_install_dir() {
    local data_path
    data_path=$(docker inspect foxel --format='{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}')
    if [[ -n "$data_path" ]]; then
        echo "$(dirname "$data_path")"
    fi
}

service_menu() {
    while true; do
        echo
        echo "--- 服务管理 ---"
        echo "1. 启动 Foxel"
        echo "2. 停止 Foxel"
        echo "3. 重启 Foxel"
        echo "4. 查看日志"
        echo "5. 返回上级菜单"
        read -p "请选择操作 [1-5]: " service_choice
        case $service_choice in
            1) info "正在启动..."; $COMPOSE_CMD up -d ;;
            2) info "正在停止..."; $COMPOSE_CMD stop ;;
            3) info "正在重启..."; $COMPOSE_CMD restart ;;
            4) info "正在显示日志 (按 Ctrl+C 退出)..."; $COMPOSE_CMD logs -f ;;
            5) break ;;
            *) warn "无效输入。" ;;
        esac
    done
}

manage_existing_installation() {
    info "检测到 Foxel 已安装。"
    local foxel_dir
    foxel_dir=$(get_foxel_install_dir)

    if [[ -z "$foxel_dir" || ! -f "$foxel_dir/compose.yaml" ]]; then
        error "无法自动定位 Foxel 的 compose.yaml 文件。"
        read -p "请手动输入 Foxel 的安装目录 (包含 compose.yaml 的目录): " foxel_dir
        if [[ ! -f "$foxel_dir/compose.yaml" ]]; then error "在指定目录中未找到 compose.yaml。退出。"; exit 1; fi
    fi
    info "Foxel 安装目录位于: $foxel_dir"
    cd "$foxel_dir" || exit 1

    while true; do
        echo
        echo "--- Foxel 管理菜单 ---"
        echo "1. 更新"
        echo "2. 卸载"
        echo "3. 重新安装"
        echo "4. 服务管理 (启动/停止/重启/日志)"
        echo "5. 退出"
        read -p "请选择操作 [1-5]: " choice

        case $choice in
            1) # 更新
                warn "更新前，强烈建议您备份 '$foxel_dir/data' 目录！"
                if confirm_action "您确定要继续更新吗？"; then
                    info "正在拉取最新镜像..."
                    $COMPOSE_CMD pull
                    info "正在使用新镜像重新部署..."
                    $COMPOSE_CMD up -d
                    if [ $? -eq 0 ]; then info "Foxel 更新成功！"; else error "更新失败！"; fi
                else info "更新操作已取消。"; fi
                ;;
            2) # 卸载
                warn "这将停止并删除 Foxel 容器及相关网络！"
                warn "强烈建议您先备份 '$foxel_dir/data' 目录！"
                if confirm_action "您确定要继续卸载吗？"; then
                    info "正在停止并移除容器..."
                    $COMPOSE_CMD down
                    if confirm_action "是否要删除所有数据卷（这将删除数据库等所有数据）？"; then
                         $COMPOSE_CMD down -v
                         info "数据卷已删除。"
                    fi
                    if confirm_action "是否要删除整个 Foxel 安装目录 '$foxel_dir'？"; then
                        rm -rf "$foxel_dir"
                        info "安装目录已删除。"
                    fi
                    info "Foxel 卸载完成。"
                    exit 0
                else info "卸载操作已取消。"; fi
                ;;
            3) # 重新安装
                warn "重新安装将完全删除当前的 Foxel 实例（包括数据），然后进入全新安装流程。"
                warn "在继续之前，请务必备份好您的重要数据！"
                if confirm_action "您确定要重新安装吗？"; then
                    info "正在执行卸载..."
                    $COMPOSE_CMD down -v && rm -rf "$foxel_dir"
                    info "旧实例已彻底移除。"
                    install_new_foxel
                    exit 0
                else info "重新安装操作已取消。"; fi
                ;;
            4) # 服务管理
                service_menu
                ;;
            5) # 退出
                break
                ;;
            *)
                warn "无效输入。"
                ;;
        esac
    done
}

# --- 主函数 ---
main() {
    clear
    local SCRIPT_VERSION="1.7"
    echo "================================================="
    info "欢迎使用 Foxel 一键安装与管理脚本 (版本: ${SCRIPT_VERSION})"
    echo "================================================="
    echo

    initialize_environment
    echo

    if docker ps -a -q -f "name=^/foxel$" | grep -q .; then
        manage_existing_installation
    else
        install_new_foxel
    fi

    echo
    info "脚本执行完毕。"
}

# --- 脚本入口 ---
main
