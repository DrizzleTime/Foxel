# 插件运行约定

Foxel 当前只支持受信任插件。安装权限等同于执行宿主代码：Python 后端直接在主进程运行；iframe 用于渲染和样式隔离，同源且无 sandbox，可以访问父页面和登录存储。安装前应审核来源及代码。此架构不支持不受信任的第三方代码；此类支持需要独立来源的前端、能力授权和独立后端进程。

匿名资源接口只发布 manifest.frontend.publicDir（默认 frontend）中的文件，以及 frontend.entry、styles、icon、assets 明确列出的文件。publicDir 不得为插件根目录；manifest、隐藏文件、Python 文件及声明的后端入口不会发布。后台代码及其他未公开文件不应放入前端目录。

宿主请求使用 protocol=1 的 request/result 消息，核对 origin、source、pluginKey 和请求 ID。host.close/openPath/openFile 返回 Promise，失败会拒绝。路径必须是 VFS 绝对路径，openFile 可指定应用 key（插件 key 或 plugin: 前缀）。

挂载函数返回的清理函数是首选卸载契约；没有返回清理函数时，兼容调用文件模式的 unmount 或应用模式的 unmountApp，两者不会重复调用。关闭时先标记失效，异步挂载完成后立即清理。宿主保留隐藏 iframe 等待卸载确认，最多等待 5 秒，之后强制释放文档。

数据库的 manifest、version、active_directory 是激活版本的唯一依据。目录入口只是兼容链接；资源读取和启动均使用数据库选定的独立版本目录。旧目录会在首次启动时迁移。磁盘 manifest 不匹配时进入 failed 并保存 last_error，不会静默切换来源。升级失败保留原激活版本及运行状态，并持久化本次错误；没有旧版本的组件安装失败会保留 failed 记录供查看。

状态包括 disabled、loading、active、failed；管理 API PATCH /api/plugins/{key}/enabled 接收 {"enabled": true/false}。只有 active 插件注册为前端应用。安装和启动会检查 foxpkg=1.0、合法的版本号、hostApiVersion（默认 >=1.0,<2.0）、dependencies.python 和已安装的包版本；不会自动安装 Python 依赖。版本范围使用 PEP 440，包声明使用 PEP 508；URL 和 extras 依赖须改为可验证的具体包要求。

插件管理器及处理器注册表为进程内状态，部署应使用单个应用进程；多进程部署需要额外的版本广播和各工作进程的同步激活机制。
