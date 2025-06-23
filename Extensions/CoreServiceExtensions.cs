using Foxel.Services;
using Foxel.Services.AI;
using Foxel.Services.Auth;
using Foxel.Services.Background;
using Foxel.Services.Background.Processors;
using Foxel.Services.Configuration;
using Foxel.Services.Initializer;
using Foxel.Services.Management;
using Foxel.Services.Mapping;
using Foxel.Services.Media;
using Foxel.Services.Storage;
using Foxel.Services.VectorDb;

namespace Foxel.Extensions;

/// <summary>
/// 核心业务服务相关的扩展方法
/// </summary>
public static class CoreServiceExtensions
{
    /// <summary>
    /// 添加核心业务服务
    /// </summary>
    public static IServiceCollection AddCoreServices(this IServiceCollection services)
    {
        // 配置服务
        services.AddSingleton<IConfigService, ConfigService>();
        
        // 核心业务服务
        services.AddSingleton<IAiService, AiService>();
        services.AddSingleton<IPictureService, PictureService>();
        services.AddSingleton<IAuthService, AuthService>();
        services.AddSingleton<ITagService, TagService>();
        services.AddSingleton<IAlbumService, AlbumService>();
        services.AddSingleton<IStorageService, StorageService>();
        services.AddSingleton<IMappingService, MappingService>();
        
        return services;
    }

    /// <summary>
    /// 添加管理服务
    /// </summary>
    public static IServiceCollection AddManagementServices(this IServiceCollection services)
    {
        services.AddSingleton<IUserManagementService, UserManagementService>();
        services.AddSingleton<IPictureManagementService, PictureManagementService>();
        services.AddSingleton<IAlbumManagementService, AlbumManagementService>();
        services.AddSingleton<ILogManagementService, LogManagementService>();
        services.AddSingleton<IStorageManagementService, StorageManagementService>();
        services.AddSingleton<IFaceManagementService, FaceManagementService>();
        
        return services;
    }

    /// <summary>
    /// 添加后台任务服务
    /// </summary>
    public static IServiceCollection AddBackgroundServices(this IServiceCollection services)
    {
        services.AddSingleton<IBackgroundTaskQueue, BackgroundTaskQueue>();
        services.AddHostedService<QueuedHostedService>();
        
        // 任务处理器
        services.AddSingleton<PictureTaskProcessor>();
        services.AddSingleton<FaceRecognitionTaskProcessor>();
        services.AddSingleton<VisualRecognitionTaskProcessor>();
        
        return services;
    }

    /// <summary>
    /// 添加AI和向量数据库服务
    /// </summary>
    public static IServiceCollection AddAiServices(this IServiceCollection services)
    {
        services.AddSingleton<IFaceClusteringService, FaceClusteringService>();
        services.AddSingleton<VectorDbManager>();
        services.AddSingleton<IVectorDbService>(provider =>
            provider.GetRequiredService<VectorDbManager>());
        services.AddHostedService<VectorDbInitializer>();
        
        return services;
    }

    /// <summary>
    /// 添加初始化服务
    /// </summary>
    public static IServiceCollection AddInitializationServices(this IServiceCollection services)
    {
        services.AddSingleton<IDatabaseInitializer, DatabaseInitializer>();
        return services;
    }
}
