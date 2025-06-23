using Foxel.Services.Initializer;

namespace Foxel.Extensions;

/// <summary>
/// 应用程序配置扩展方法
/// </summary>
public static class ApplicationConfigurationExtensions
{
    /// <summary>
    /// 配置应用程序中间件管道
    /// </summary>
    public static WebApplication ConfigureApplicationPipeline(this WebApplication app)
    {
        // 转发头处理
        app.UseForwardedHeaders();
        
        // 静态文件
        app.UseApplicationStaticFiles();
        
        // 开发环境特定配置
        if (!app.Environment.IsDevelopment())
        {
            app.UseExceptionHandler("/Error", createScopeForErrors: true);
            app.UseHsts();
        }
        
        // API文档
        app.UseApplicationOpenApi();
        
        // CORS
        app.UseCors("MyAllowSpecificOrigins");
        
        // 身份验证和授权
        app.UseAuthentication();
        app.UseAuthorization();
        
        // 路由
        app.MapControllers();
        app.UseHttpsRedirection();
        
        return app;
    }

    /// <summary>
    /// 初始化应用程序
    /// </summary>
    public static async Task<WebApplication> InitializeApplicationAsync(this WebApplication app)
    {
        using var scope = app.Services.CreateScope();
        var initializer = scope.ServiceProvider.GetRequiredService<IDatabaseInitializer>();
        await initializer.InitializeAsync();
        
        return app;
    }
}
