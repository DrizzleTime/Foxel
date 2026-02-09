<div align="right">
  <b>English</b> | <a href="./README_zh.md">简体中文</a>
</div>

<div align="center">

# Foxel

**A highly extensible private cloud storage solution for individuals and teams, featuring AI-powered semantic search.**

![Python Version](https://img.shields.io/badge/Python-3.14+-blue.svg)
![React](https://img.shields.io/badge/React-19.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

![GitHub stars](https://img.shields.io/github/stars/DrizzleTime/foxel?style=social)

---
  <blockquote>
    <em><strong>The ocean of data is boundless, let the eye of insight guide the voyage, yet its intricate connections lie deep, not fully discernible from the surface.</strong></em>
  </blockquote>
  <img src="https://foxel.cc/image/ad-min-en.png" alt="UI Screenshot">
</div>

## 👀 Online Demo

> [https://demo.foxel.cc](https://demo.foxel.cc)
>
> Account/Password: `admin` / `admin`

## ✨ Core Features

### 📁 Unified File Management

Centralize management of files distributed across different storage backends. Browse, upload, download, move, copy, and delete — all through a single, unified interface.

### 🔌 Pluggable Storage Backends

Utilizes an extensible adapter pattern to easily integrate various storage types:

| Category | Adapters |
|---|---|
| **Standard Protocols** | Local, S3-compatible, WebDAV, SFTP, FTP |
| **Cloud Drives** | Google Drive, OneDrive, Dropbox, Quark |
| **Special** | Telegram, AList, Foxel-to-Foxel |

### 🔍 AI-Powered Semantic Search

Go beyond filename matching — search by natural language descriptions to find content within images, documents, and other unstructured data. Powered by configurable embedding providers and vector databases (Milvus, Qdrant).

### 👁️ Built-in File Preview

Preview images, videos, PDFs, Office documents, text, and code files directly in the browser — no downloads required.

### 🔐 Permissions & Access Control

A full-featured **Role-Based Access Control (RBAC)** system to secure your data:

- **Built-in Roles**: Three system roles — **Admin** (full access), **User** (configurable access), and **Viewer** (read-only).
- **Custom Roles**: Create tailored roles with fine-grained system and adapter permissions.
- **Path-based Rules**: Define read / write / delete / share permissions per path, with support for **wildcards**, **regex patterns**, and **priority-based rule ordering**.
- **Audit Logging**: Every user action is recorded with full traceability (user, IP, method, status, duration).
### 🔗 Sharing

Generate public or password-protected share links with configurable expiration dates. Recipients can browse shared files and folders without logging in.

### 🧩 Plugin System

Extend Foxel's capabilities through a manifest-based plugin architecture. Load React frontend components and custom backend routes at runtime, without modifying the core codebase.

### ⚙️ Task Processing Center

Run asynchronous background tasks — file indexing, data backups, scheduled jobs — without impacting the main application.

### 🤖 AI Agent

An integrated AI agent with built-in tools for VFS operations, web fetching, and file processing — bringing intelligent automation directly into your cloud storage.

### 🌐 Protocol Mappings

Access your files through familiar protocols:

- **S3 API** — S3-compatible endpoint for programmatic access
- **WebDAV** — Mount as a network drive in your OS file manager
- **Direct Links** — Temporary signed URLs for direct file access

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.14+, FastAPI, Tortoise ORM, SQLite |
| **Frontend** | React 19, TypeScript, Vite, Ant Design |
| **Auth** | JWT (OAuth2), bcrypt |
| **Vector DB** | Milvus Lite / Server, Qdrant |
| **Deployment** | Docker, Gunicorn + Uvicorn |
| **Package Managers** | uv (Python), Bun (JS) |

## 🚀 Quick Start

Using Docker Compose is the most recommended way to start Foxel.

### 1. Create Data Directories

Create a `data` folder for persistent data:

```bash
mkdir -p data/db data/mount
chmod 777 data/db data/mount
```

### 2. Download Docker Compose File

```bash
curl -L -O https://github.com/DrizzleTime/Foxel/raw/main/compose.yaml
```

After downloading, it is **strongly recommended** to modify the environment variables in the `compose.yaml` file to ensure security:

- Modify `SECRET_KEY` and `TEMP_LINK_SECRET_KEY`: Replace the default keys with randomly generated strong keys.

### 3. Start the Services

```bash
docker-compose up -d
```

### 4. Access the Application

Once the services are running, open the page in your browser.

> On the first launch, please follow the setup guide to initialize the administrator account.

## 🤝 How to Contribute

We welcome contributions from the community! Whether it's submitting bugs, suggesting new features, or contributing code directly.

Before you start, please read our [`CONTRIBUTING.md`](CONTRIBUTING.md) file, which explains the development environment and submission process. A Simplified Chinese translation is available in [`CONTRIBUTING_zh.md`](CONTRIBUTING_zh.md).

## 🌐 Community

Join our community on [Telegram](https://t.me/+thDsBfyqJxZkNTU1) to discuss with developers and other users!

You can also join our WeChat group for more real-time communication and support. Please scan the QR code below to join:

<img src="https://foxel.cc/image/wechat.png" alt="WeChat Group QR Code" width="180">

> If the QR code is invalid, please add WeChat ID **drizzle2001**, and we will invite you to the group.

## 📄 License

Foxel is open-sourced under the [MIT License](LICENSE).
