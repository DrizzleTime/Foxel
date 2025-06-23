namespace Foxel.Extensions;

/// <summary>
/// 应用程序服务配置扩展方法
/// </summary>
public static class ApplicationServiceExtensions
{
    /// <summary>
    /// 添加所有应用程序服务
    /// </summary>
    public static IServiceCollection AddApplicationServices(this IServiceCollection services, IConfiguration configuration)
    {
        // 基础服务
        services.AddControllers();
        services.AddHttpServices();
        
        // 数据库
        services.AddApplicationDbContext(configuration);
        
        // 核心业务服务
        services.AddCoreServices();
        services.AddManagementServices();
        services.AddBackgroundServices();
        services.AddAiServices();
        services.AddInitializationServices();
        
        // 身份验证和授权
        services.AddApplicationAuthentication();
        services.AddApplicationAuthorization();
        services.AddApplicationCors();
        
        // API文档
        services.AddApplicationOpenApi();
        
        // HTTP相关
        services.AddForwardedHeaders();
        
        return services;
    }
}
