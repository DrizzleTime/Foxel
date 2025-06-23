using Microsoft.EntityFrameworkCore;

namespace Foxel.Extensions;

/// <summary>
/// 数据库相关的扩展方法
/// </summary>
public static class DatabaseExtensions
{
    /// <summary>
    /// 添加应用程序数据库上下文
    /// </summary>
    public static IServiceCollection AddApplicationDbContext(this IServiceCollection services, IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("DefaultConnection");
        if (string.IsNullOrEmpty(connectionString))
        {
            connectionString = Environment.GetEnvironmentVariable("DEFAULT_CONNECTION");
        }

        Console.WriteLine($"数据库连接: {connectionString}");
        services.AddDbContextFactory<MyDbContext>(options =>
            options.UseNpgsql(connectionString));
            
        return services;
    }
}
