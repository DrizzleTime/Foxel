<div align="right">
  <b>English</b> | <a href="./CONTRIBUTING_zh.md">简体中文</a>
</div>

# Contributing to Foxel

We appreciate every minute you spend helping Foxel improve. This guide explains the contribution workflow so you can get started quickly.

## Table of Contents

- [How to Contribute](#how-to-contribute)
  - [🐛 Report Bugs](#-report-bugs)
  - [✨ Suggest Features](#-suggest-features)
  - [🛠️ Contribute Code](#️-contribute-code)
- [Development Environment](#development-environment)
  - [Prerequisites](#prerequisites)
  - [Backend (FastAPI)](#backend-fastapi)
  - [Frontend (React + Vite)](#frontend-react--vite)
- [Contribution Guidelines](#contribution-guidelines)
  - [Storage Adapters](#storage-adapters)
  - [Frontend Apps](#frontend-apps)
- [Submission Rules](#submission-rules)
  - [Git Branching](#git-branching)
  - [Commit Message Format](#commit-message-format)
  - [Pull Request Flow](#pull-request-flow)

---

## How to Contribute

### 🐛 Report Bugs

If you discover a bug, open a ticket via [GitHub Issues](https://github.com/DrizzleTime/Foxel/issues) and include:

- **A clear title** that summarises the problem.
- **Reproduction steps** with enough detail to trigger the bug.
- **Expected vs actual behaviour** to highlight the gap.
- **Environment details** such as operating system, browser version, and the Foxel build you used.

### ✨ Suggest Features

To propose a new capability or an improvement, create an Issue and choose the "Feature Request" template. Document:

- **Problem statement** – what pain point will the feature solve?
- **Proposed solution** – how you expect it to work.
- **Supporting material** – screenshots, references, or related links if helpful.

### 🛠️ Contribute Code

Follow the development setup below before opening a pull request. Keep changes focused and small so they are easier to review.

## Development Environment

### Prerequisites

Install the following tooling first:

- **Git** for version control
- **Python** 3.13 or newer
- **Bun** for frontend package management and scripts

### Backend (FastAPI)

1. **Clone the repository**

    ```bash
    git clone https://github.com/DrizzleTime/foxel.git
    cd Foxel
    ```

2. **Create and activate a virtual environment**

    `uv` is recommended for performance and reproducibility:

    ```bash
    uv venv
    source .venv/bin/activate
    # On Windows: .venv\Scripts\activate
    ```

3. **Install dependencies**

    ```bash
    uv sync
    ```

4. **Prepare local resources**

    - Create the data directory:

      ```bash
      mkdir -p data/db
      ```

      Ensure the application user can read and write to `data/db`.

    - Create an `.env` file in the project root and provide the required secrets. Replace the sample values with your own random strings:

      ```dotenv
      SECRET_KEY=EnsRhL9NFPxgFVc+7t96/y70DIOR+9SpntcIqQa90TU=
      TEMP_LINK_SECRET_KEY=EnsRhL9NFPxgFVc+7t96/y70DIOR+9SpntcIqQa90TU=
      ```

5. **Start the development server**

    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    The API is available at `http://localhost:8000`, and the interactive docs live at `http://localhost:8000/docs`.

### Frontend (React + Vite)

1. **Enter the frontend directory**

    ```bash
    cd web
    ```

2. **Install dependencies**

    ```bash
    bun install
    ```

3. **Run the dev server**

    ```bash
    bun run dev
    ```

    The Vite dev server runs at `http://localhost:5173` and proxies `/api` requests to the backend.

## Contribution Guidelines

### Storage Adapters

Storage adapters integrate new storage providers (for example S3, FTP, or Alist).

1. Create a new module under [`domain/adapters/providers/`](domain/adapters/providers/) (for example `my_new_adapter.py`).
2. Implement a class that inherits from [`domain.adapters.providers.base.BaseAdapter`](domain/adapters/providers/base.py) and provide concrete implementations for the abstract methods such as `list_dir`, `get_meta`, `upload`, and `download`.

### Frontend Apps

Frontend apps enable in-browser previews or editors for specific file types.

1. Add a new folder in [`web/src/apps/`](web/src/apps/) for your app and expose a React component.
2. Implement the `FoxelApp` interface defined in [`web/src/apps/types.ts`](web/src/apps/types.ts).
3. Register the app in [`web/src/apps/registry.ts`](web/src/apps/registry.ts) and declare the MIME types or extensions it supports.

## Submission Rules

### Git Branching

Start your work from the latest `main` branch and push feature changes on a dedicated branch.

### Commit Message Format

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification to drive release tooling.

```
<type>(<scope>): <subject>
<BLANK LINE>
<body>
<BLANK LINE>
<footer>
```

- **type**: e.g. `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
- **scope** (optional): the area impacted by the change, such as `adapter`, `ui`, or `api`.
- **subject**: a concise summary written in the imperative mood.

**Examples:**

```
feat(adapter): add support for Alist storage
```

```
fix(ui): correct display issue in file list view
```

### Pull Request Flow

1. Fork the repository and clone it locally.
2. Create and switch to your feature branch.
3. Implement the change and run relevant checks.
4. Push the branch to your fork.
5. Open a pull request against `main` in the Foxel repository.
6. Explain the change set, its motivation, and reference related Issues in the PR description.

Maintainers will review your pull request as soon as possible.
