<div align="right">
  <a href="./CONTRIBUTING.md">English</a> | <b>简体中文</b>
</div>

# Contributing to Foxel

🎉 首先，非常感谢您愿意花时间为 Foxel 做出贡献！

我们热烈欢迎各种形式的贡献。无论是报告 Bug、提出新功能建议、完善文档，还是直接提交代码，都将对项目产生积极的影响。

本指南将帮助您顺利地参与到项目中来。

## 目录

- [如何贡献](#如何贡献)
  - [🐛 报告 Bug](#-报告-bug)
  - [✨ 提交功能建议](#-提交功能建议)
  - [🛠️ 贡献代码](#️-贡献代码)
- [开发环境搭建](#开发环境搭建)
  - [依赖准备](#依赖准备)
  - [后端 (FastAPI)](#后端-fastapi)
  - [前端 (React + Vite)](#前端-react--vite)
- [代码贡献指南](#代码贡献指南)
  - [贡献存储适配器 (Adapter)](#贡献存储适配器-adapter)
  - [贡献前端应用 (App)](#贡献前端应用-app)
- [提交规范](#提交规范)
  - [Git 分支管理](#git-分支管理)
  - [Commit Message 格式](#commit-message-格式)
  - [Pull Request 流程](#pull-request-流程)

---

## 如何贡献

### 🐛 报告 Bug

如果您在使用的过程中发现了 Bug，请通过 [GitHub Issues](https://github.com/DrizzleTime/Foxel/issues) 来报告。请在报告中提供以下信息：

- **清晰的标题**：简明扼要地描述问题。
- **复现步骤**：详细说明如何一步步重现该 Bug。
- **期望行为** vs **实际行为**：描述您预期的结果和实际发生的情况。
- **环境信息**：例如操作系统、浏览器版本、Foxel 版本等。

### ✨ 提交功能建议

我们欢迎任何关于新功能或改进的建议。请通过 [GitHub Issues](https://github.com/DrizzleTime/Foxel/issues) 创建一个 "Feature Request"，并详细阐述您的想法：

- **问题描述**：说明该功能要解决什么问题。
- **方案设想**：描述您希望该功能如何工作。
- **相关信息**：提供任何有助于理解您想法的截图、链接或参考。

### 🛠️ 贡献代码

如果您希望直接贡献代码，请参考下面的开发和提交流程。

## 开发环境搭建

### 依赖准备

- **Git**: 用于版本控制。
- **Python**: >= 3.13
- **Bun**: 用于前端包管理和脚本运行。

### 后端 (FastAPI)

后端 API 服务基于 Python 和 FastAPI 构建。

1. **克隆仓库**

    ```bash
    git clone https://github.com/DrizzleTime/foxel.git
    cd Foxel
    ```

2. **创建并激活 Python 虚拟环境**

    我们推荐使用 `uv` 来管理虚拟环境，以获得最佳性能。

    ```bash
    uv venv
    source .venv/bin/activate
    # On Windows: .venv\Scripts\activate
    ```

3. **安装依赖**

    ```bash
    uv sync
    ```

4. **初始化环境**

    在启动服务前，请进行以下准备：

    - **创建数据目录**:
      在项目根目录执行 `mkdir -p data/db`。这将创建用于存放数据库等文件的目录。
      > [!IMPORTANT]
      > 请确保应用拥有对 `data/db` 目录的读写权限。

    - **创建 `.env` 配置文件**:
      在项目根目录创建名为 `.env` 的文件，并填入以下内容。这些密钥用于保障应用安全，您可以按需修改。

      ```dotenv
      SECRET_KEY=EnsRhL9NFPxgFVc+7t96/y70DIOR+9SpntcIqQa90TU=
      TEMP_LINK_SECRET_KEY=EnsRhL9NFPxgFVc+7t96/y70DIOR+9SpntcIqQa90TU=
      ```

5. **启动开发服务器**

    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    API 服务将在 `http://localhost:8000` 上运行，您可以通过 `http://localhost:8000/docs` 访问自动生成的 API 文档。

### 前端 (React + Vite)

前端应用使用 React, Vite, 和 TypeScript 构建。

1. **进入前端目录**

    ```bash
    cd web
    ```

2. **安装依赖**

    ```bash
    bun install
    ```

3. **启动开发服务器**

    ```bash
    bun run dev
    ```

    前端开发服务器将在 `http://localhost:5173` 运行。它已经配置了代理，会自动将 `/api` 请求转发到后端服务。

## 代码贡献指南

### 贡献存储适配器 (Adapter)

存储适配器是 Foxel 的核心扩展点，用于接入不同的存储后端 (如 S3, FTP, Alist 等)。

1. **创建适配器文件**: 在 [`domain/adapters/providers/`](domain/adapters/providers/) 目录下，创建一个新文件，例如 `my_new_adapter.py`。
2. **实现适配器类**:
    - 创建一个类，继承自 [`domain.adapters.providers.base.BaseAdapter`](domain/adapters/providers/base.py)。
    - 实现 `BaseAdapter` 中定义的所有抽象方法，如 `list_dir`, `get_meta`, `upload`, `download` 等。请仔细阅读基类中的文档注释以理解每个方法的作用和参数。

### 贡献前端应用 (App)

前端应用允许用户在浏览器中直接预览或编辑特定类型的文件。

1. **创建应用组件**: 在 [`web/src/apps/`](web/src/apps/) 目录下，为您的应用创建一个新的文件夹，并在其中创建 React 组件。
2. **定义应用类型**: 您的应用需要实现 [`web/src/apps/types.ts`](web/src/apps/types.ts) 中定义的 `FoxelApp` 接口。
3. **注册应用**: 在 [`web/src/apps/registry.ts`](web/src/apps/registry.ts) 中，导入您的应用组件，并将其添加到 `APP_REGISTRY`。在注册时，您需要指定该应用可以处理的文件类型（通过 MIME Type 或文件扩展名）。

## 提交规范

### Git 分支管理

- 从最新的 `main` 分支创建您的特性分支。

### Commit Message 格式

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。这有助于自动化生成更新日志和版本管理。

Commit Message 格式如下:

```
<type>(<scope>): <subject>
<BLANK LINE>
<body>
<BLANK LINE>
<footer>
```

- **type**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore` 等。
- **scope**: (可选) 本次提交影响的范围，例如 `adapter`, `ui`, `api`。
- **subject**: 简明扼要的描述。

**示例:**

```
feat(adapter): Add support for Alist storage
```

```
fix(ui): Correct display issue in file list view
```

### Pull Request 流程

1. Fork 仓库并克隆到本地。
2. 创建并切换到您的特性分支。
3. 完成代码编写和测试。
4. 将您的分支推送到您的 Fork 仓库。
5. 在 Foxel 主仓库创建一个 Pull Request，目标分支为 `main`。
6. 在 PR 描述中清晰地说明您的更改内容、目的和任何相关的 Issue 编号。

项目维护者会尽快审查您的 PR。感谢您的耐心和贡献！
