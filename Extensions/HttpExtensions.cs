using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.FileProviders;

namespace Foxel.Extensions;

/// <summary>
/// HTTP相关的扩展方法
/// </summary>
public static class HttpExtensions
{
    /// <summary>
    /// 添加HTTP相关服务
    /// </summary>
    public static IServiceCollection AddHttpServices(this IServiceCollection services)
    {
        services.AddHttpClient();
        services.AddHttpContextAccessor();
        services.AddMemoryCache();
        return services;
    }

    /// <summary>
    /// 配置转发头信息
    /// </summary>
    public static IServiceCollection AddForwardedHeaders(this IServiceCollection services)
    {
        services.Configure<ForwardedHeadersOptions>(options =>
        {
            options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
            options.KnownNetworks.Clear();
            options.KnownProxies.Clear();
        });
        
        return services;
    }

    /// <summary>
    /// 使用应用程序静态文件
    /// </summary>
    public static WebApplication UseApplicationStaticFiles(this WebApplication app)
    {
        var uploadsPath = Path.Combine(Directory.GetCurrentDirectory(), "Uploads");
        if (!Directory.Exists(uploadsPath))
        {
            Directory.CreateDirectory(uploadsPath);
        }

        app.UseStaticFiles(new StaticFileOptions
        {
            FileProvider = new PhysicalFileProvider(uploadsPath),
            RequestPath = "/Uploads"
        });
        
        return app;
    }
}
