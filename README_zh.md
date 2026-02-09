<div align="right">
  <a href="./README.md">English</a> | <b>简体中文</b>
</div>

<div align="center">

# Foxel

**一个面向个人和团队的、高度可扩展的私有云盘解决方案，支持 AI 语义搜索。**

![Python Version](https://img.shields.io/badge/Python-3.14+-blue.svg)
![React](https://img.shields.io/badge/React-19.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

![GitHub stars](https://img.shields.io/github/stars/DrizzleTime/foxel?style=social)

---
  <blockquote>
    <em><strong>数据之洋浩瀚无涯，当以洞察之目引航，然其脉络深隐，非表象所能尽窥。</strong></em><br>
  </blockquote>
  <img src="https://foxel.cc/image/ad-min-zh.png" alt="UI Screenshot">
</div>

## 👀 在线体验

> [https://demo.foxel.cc](https://demo.foxel.cc)
>
> 账号/密码：`admin` / `admin`

## ✨ 核心功能

### 📁 统一文件管理

集中管理分布于不同存储后端的文件。浏览、上传、下载、移动、复制和删除——全部通过统一的界面完成。

### 🔌 插件化存储后端

采用可扩展的适配器模式，方便集成多种存储类型：

| 分类 | 适配器 |
|---|---|
| **标准协议** | 本地存储、S3 兼容存储、WebDAV、SFTP、FTP |
| **网盘服务** | Google Drive、OneDrive、Dropbox、夸克网盘 |
| **特殊类型** | Telegram、AList、Foxel 互联 |

### 🔍 AI 语义搜索

突破文件名匹配的局限——通过自然语言描述搜索图片、文档等非结构化数据的内容。由可配置的 Embedding 服务和向量数据库（Milvus、Qdrant）驱动。

### 👁️ 内置文件预览

可直接在浏览器中预览图片、视频、PDF、Office 文档及文本、代码文件，无需下载。

### 🔐 权限与访问控制

完善的 **基于角色的访问控制（RBAC）** 系统，全方位保障数据安全：

- **内置角色**：三个系统角色 — **管理员**（完全访问）、**用户**（可配置访问权限）、**观察者**（只读访问）。
- **自定义角色**：可创建自定义角色，灵活分配系统权限和适配器权限。
- **路径级权限规则**：为每个路径定义 读取 / 写入 / 删除 / 分享 权限，支持 **通配符**、**正则表达式** 匹配和 **优先级排序**。
- **审计日志**：记录所有用户操作，包含完整的追溯信息（用户、IP、请求方法、状态码、耗时）。
### 🔗 文件分享

生成公开或加密的分享链接，支持设置过期时间。接收方无需登录即可浏览分享的文件和文件夹。

### 🧩 插件系统

通过基于清单（Manifest）的插件架构扩展 Foxel 的功能。支持在运行时加载 React 前端组件和自定义后端路由，无需修改核心代码。

### ⚙️ 任务处理中心

支持异步后台任务——文件索引、数据备份、定时作业——不影响主应用运行。

### 🤖 AI 智能助手

内置 AI Agent，提供 VFS 操作、网页抓取、文件处理等工具，将智能自动化能力直接融入你的云盘。

### 🌐 协议映射

通过熟悉的协议访问你的文件：

- **S3 API** — S3 兼容接口，支持编程方式访问
- **WebDAV** — 可在操作系统文件管理器中挂载为网络硬盘
- **直链** — 临时签名 URL，支持直接文件访问

## 🛠️ 技术栈

| 层级 | 技术 |
|---|---|
| **后端** | Python 3.14+、FastAPI、Tortoise ORM、SQLite |
| **前端** | React 19、TypeScript、Vite、Ant Design |
| **认证** | JWT（OAuth2）、bcrypt |
| **向量数据库** | Milvus Lite / Server、Qdrant |
| **部署** | Docker、Gunicorn + Uvicorn |
| **包管理** | uv（Python）、Bun（JS） |

## 🚀 快速开始

使用 Docker Compose 是启动 Foxel 最推荐的方式。

### 1. 创建数据目录

新建 `data` 文件夹用于持久化数据：

```bash
mkdir -p data/db data/mount
chmod 777 data/db data/mount
```

### 2. 下载 Docker Compose 文件

```bash
curl -L -O https://github.com/DrizzleTime/Foxel/raw/main/compose.yaml
```

下载完成后，**强烈建议**修改 `compose.yaml` 文件中的环境变量以确保安全：

- 修改 `SECRET_KEY` 和 `TEMP_LINK_SECRET_KEY`：将默认的密钥替换为随机生成的强密钥。

### 3. 启动服务

```bash
docker-compose up -d
```

### 4. 访问应用

服务启动后，在浏览器中打开页面。

> 首次启动，请根据引导页面完成管理员账号的初始化设置。

## 🤝 如何贡献

我们非常欢迎来自社区的贡献！无论是提交 Bug、建议新功能还是直接贡献代码。

在开始之前，请先阅读我们的 [`CONTRIBUTING_zh.md`](CONTRIBUTING_zh.md) 文件，它会指导你如何设置开发环境以及提交流程。

## 🌐 社区

加入我们的交流社区：[Telegram 群组](https://t.me/+thDsBfyqJxZkNTU1)，与开发者和用户一起讨论！

你也可以加入我们的微信群，获取更多实时交流与支持。请扫描下方二维码加入：

<img src="https://foxel.cc/image/wechat.png" alt="微信群二维码" width="180">

> 如果二维码失效，请添加微信号 **drizzle2001**，我们会邀请你加入群聊。

## 📄 许可证

Foxel 基于 [MIT 许可证](LICENSE) 开源。
