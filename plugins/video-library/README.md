# 视频库插件

影视刮削与媒体库管理插件，支持从 TMDB 获取电影和电视剧的元数据信息。

## 功能

- **影视刮削**：通过处理器自动从 TMDB 获取影视元数据
- **媒体库浏览**：独立应用模式，展示已刮削的影视库
- **视频播放**：支持常见视频格式的播放

## 使用方法

### 作为处理器

1. 在"处理器"页面选择"影视入库"处理器
2. 选择视频文件或包含电视剧的目录
3. 配置语言等选项
4. 执行处理，自动获取 TMDB 元数据

### 作为应用

1. 在"应用"中打开"视频库"
2. 浏览已刮削的影视内容
3. 点击播放观看

## 配置

### TMDB API

需要在环境变量中配置 TMDB 认证信息：

```bash
TMDB_ACCESS_TOKEN=your_access_token
# 或
TMDB_API_KEY=your_api_key
```

## 开发

### 目录结构

```
video-library/
├── manifest.json           # 插件元数据
├── frontend/
│   └── index.js            # 前端入口（编译后）
├── backend/
│   ├── routes/
│   │   └── api.py          # API 路由
│   └── processors/
│       └── video_library.py # 处理器
└── assets/
    └── icon.svg            # 图标
```

### 打包

```bash
cd plugins/video-library
zip -r ../video-library.foxpkg .
```

## 许可证

MIT

