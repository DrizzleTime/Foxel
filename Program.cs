using Foxel.Extensions;

var builder = WebApplication.CreateBuilder(args);
var environment = builder.Environment;

Console.WriteLine($"当前环境: {environment.EnvironmentName}");

// 配置日志记录
builder.Logging.AddDatabaseLogging(config =>
{
    config.MinLevel = LogLevel.Information; 
    config.Enabled = true;
});

// 添加所有应用程序服务
builder.Services.AddApplicationServices(builder.Configuration);

var app = builder.Build();

// 初始化应用程序
await app.InitializeApplicationAsync();

// 配置中间件管道
app.ConfigureApplicationPipeline();

// 启动应用程序
app.Run();