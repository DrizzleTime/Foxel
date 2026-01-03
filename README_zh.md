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

- **统一文件管理**：集中管理分布于不同存储后端的文件。
- **插件化存储后端**：采用可扩展的适配器模式，方便集成多种存储类型。
- **语义搜索**：支持自然语言描述搜索图片、文档等非结构化数据内容。
- **内置文件预览**：可直接预览图片、视频、PDF、Office 文档及文本、代码文件，无需下载。
- **权限与分享**：支持公开或私密分享链接，便于文件共享。
- **任务处理中心**：支持异步任务处理，如文件索引和数据备份，不影响主应用运行。

## 🚀 快速开始

使用 Docker Compose 是启动 Foxel 最推荐的方式。

1. **创建数据目录**

   新建 `data` 文件夹用于持久化数据：

   ```bash
   mkdir -p data/db
   mkdir -p data/mount
   chmod 777 data/db data/mount
   ```

2. **下载 Docker Compose 文件**

   ```bash
   curl -L -O https://github.com/DrizzleTime/Foxel/raw/main/compose.yaml
   ```

   下载完成后，**强烈建议**修改 `compose.yaml` 文件中的环境变量以确保安全：

   - 修改 `SECRET_KEY` 和 `TEMP_LINK_SECRET_KEY`：将默认的密钥替换为随机生成的强密钥

3. **启动服务**

   ```bash
   docker-compose up -d
   ```

4. **访问应用**

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
