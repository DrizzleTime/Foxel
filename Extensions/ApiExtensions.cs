using Scalar.AspNetCore;

namespace Foxel.Extensions;

/// <summary>
/// API相关的扩展方法
/// </summary>
public static class ApiExtensions
{
    /// <summary>
    /// 添加应用程序OpenAPI
    /// </summary>
    public static IServiceCollection AddApplicationOpenApi(this IServiceCollection services)
    {
        services.AddOpenApi(opt => { opt.AddDocumentTransformer<BearerSecuritySchemeTransformer>(); });
        return services;
    }

    /// <summary>
    /// 使用应用程序OpenAPI
    /// </summary>
    public static WebApplication UseApplicationOpenApi(this WebApplication app)
    {
        app.MapOpenApi();
        app.MapScalarApiReference();
        return app;
    }
}
