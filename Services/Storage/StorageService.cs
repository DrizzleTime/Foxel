using System.Reflection;
using Microsoft.EntityFrameworkCore; // For IDbContextFactory
using System.Text.Json; // For JsonSerializer
using Foxel.Services.Storage.Providers; // For specific config classes

namespace Foxel.Services.Storage;

/// <summary>
/// 统一的存储服务实现
/// </summary>
public class StorageService : IStorageService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<StorageService> _logger;
    private readonly Dictionary<StorageType, Type> _storageProviders = new();
    private readonly IDbContextFactory<MyDbContext> _contextFactory;

    public StorageService(
        IServiceProvider serviceProvider,
        ILogger<StorageService> logger,
        IDbContextFactory<MyDbContext> contextFactory)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _contextFactory = contextFactory;
        RegisterStorageProviders();
    }

    /// <summary>
    /// 使用反射扫描和注册所有标记了StorageProviderAttribute的存储提供者
    /// </summary>
    private void RegisterStorageProviders()
    {
        // 获取当前应用程序域中所有程序集
        var assemblies = AppDomain.CurrentDomain.GetAssemblies();

        foreach (var assembly in assemblies)
        {
            try
            {
                // 扫描每个程序集中的所有类型
                var types = assembly.GetTypes()
                    .Where(type => type is { IsClass: true, IsAbstract: false } &&
                                   type.GetInterfaces().Contains(typeof(IStorageProvider)) &&
                                   type.GetCustomAttribute<StorageProviderAttribute>() != null);

                foreach (var type in types)
                {
                    var attribute = type.GetCustomAttribute<StorageProviderAttribute>();
                    if (attribute != null)
                    {
                        // 注册存储提供者类型与对应的存储类型
                        _storageProviders[attribute.StorageType] = type;
                        _logger.LogInformation("已注册存储提供者: {StorageType} -> {ProviderType}", attribute.StorageType, type.FullName);
                    }
                }
            }
            catch (ReflectionTypeLoadException ex) // 更具体地捕获加载类型时的异常
            {
                _logger.LogWarning(ex, "扫描程序集 {AssemblyName} 时发生类型加载错误。详细信息: {LoaderExceptions}", assembly.FullName,
                    string.Join(", ", ex.LoaderExceptions.Select(e => e?.Message ?? "N/A")));
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "扫描程序集 {AssemblyName} 时发生错误", assembly.FullName);
                // 继续扫描其他程序集
            }
        }
        if (!_storageProviders.Any())
        {
            _logger.LogWarning("未能注册任何存储提供者。请检查提供者是否正确标记了 [StorageProvider] 特性并且位于扫描的程序集中。");
        }
    }

    /// <summary>
    /// 根据 StorageModeId 获取并配置提供者实例
    /// </summary>
    private IStorageProvider GetProvider(int storageModeId)
    {
        using var context = _contextFactory.CreateDbContext();
        var storageMode = context.StorageModes
                                 .AsNoTracking()
                                 .FirstOrDefault(sm => sm.Id == storageModeId);

        if (storageMode == null)
        {
            _logger.LogError("ID 为 {StorageModeId} 的 StorageMode 未找到。", storageModeId);
            throw new ArgumentException($"ID 为 {storageModeId} 的 StorageMode 未找到。");
        }

        if (!storageMode.IsEnabled)
        {
            _logger.LogWarning("StorageMode {StorageModeId} ({StorageModeName}) 未启用。", storageModeId, storageMode.Name);
            throw new InvalidOperationException($"StorageMode '{storageMode.Name}' (ID: {storageModeId}) 未启用。");
        }

        if (!_storageProviders.TryGetValue(storageMode.StorageType, out var providerType))
        {
            _logger.LogError("未找到 StorageType {StorageType} (来自 StorageMode {StorageModeId}) 的已注册提供者。", storageMode.StorageType, storageModeId);
            throw new ArgumentException($"未找到 StorageType {storageMode.StorageType} 的提供者。");
        }

        object specificConfig = DeserializeProviderConfig(storageMode.StorageType, storageMode.ConfigurationJson, storageMode.Name);

        try
        {
            return (IStorageProvider)ActivatorUtilities.CreateInstance(_serviceProvider, providerType, specificConfig);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "为 StorageMode {StorageModeName} (ID: {StorageModeId}, Type: {StorageType}) 创建提供者 {ProviderType} 的实例失败。",
                             storageMode.Name, storageModeId, storageMode.StorageType, providerType.FullName);
            throw new InvalidOperationException($"创建存储提供者 '{providerType.Name}' 失败: {ex.Message}", ex);
        }
    }

    private object DeserializeProviderConfig(StorageType storageType, string? jsonConfig, string storageModeName)
    {
        if (string.IsNullOrWhiteSpace(jsonConfig))
        {
            _logger.LogError("StorageMode '{StorageModeName}' (Type: {StorageType}) 的 ConfigurationJson 为空或空白。", storageModeName, storageType);
            throw new InvalidOperationException($"StorageMode '{storageModeName}' (Type: {storageType}) 的配置 (ConfigurationJson) 为空。");
        }

        try
        {
            switch (storageType)
            {
                case StorageType.Local:
                    return JsonSerializer.Deserialize<LocalStorageConfig>(jsonConfig)
                           ?? throw new JsonException($"无法反序列化 LocalStorageConfig。JSON: {jsonConfig}");
                case StorageType.Telegram:
                    return JsonSerializer.Deserialize<TelegramStorageConfig>(jsonConfig)
                           ?? throw new JsonException($"无法反序列化 TelegramStorageConfig。JSON: {jsonConfig}");
                case StorageType.S3:
                     return JsonSerializer.Deserialize<S3StorageConfig>(jsonConfig) 
                           ?? throw new JsonException($"无法反序列化 S3StorageConfig。JSON: {jsonConfig}");
                case StorageType.Cos:
                     return JsonSerializer.Deserialize<CosStorageConfig>(jsonConfig) 
                           ?? throw new JsonException($"无法反序列化 CosStorageConfig。JSON: {jsonConfig}");
                case StorageType.WebDAV:
                     return JsonSerializer.Deserialize<WebDavStorageConfig>(jsonConfig) 
                           ?? throw new JsonException($"无法反序列化 WebDavStorageConfig。JSON: {jsonConfig}");
                default:
                    _logger.LogError("不支持的存储类型配置反序列化: {StorageType} (来自 StorageMode '{StorageModeName}')", storageType, storageModeName);
                    throw new NotSupportedException($"不支持 StorageType {storageType} 的配置反序列化。");
            }
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "反序列化 StorageMode '{StorageModeName}' (Type: {StorageType}) 的配置失败。JSON: {JsonConfig}", storageModeName, storageType, jsonConfig);
            throw new InvalidOperationException($"StorageMode '{storageModeName}' (Type: {storageType}) 的配置格式无效。", ex);
        }
    }

    /// <summary>
    /// 在指定存储模式上执行操作
    /// </summary>
    public async Task<TResult> ExecuteAsync<TResult>(int storageModeId, Func<IStorageProvider, Task<TResult>> operation)
    {
        var provider = GetProvider(storageModeId);
        return await operation(provider);
    }

    /// <summary>
    /// 在指定存储模式上执行无返回值的操作
    /// </summary>
    public async Task ExecuteAsync(int storageModeId, Func<IStorageProvider, Task> operation)
    {
        var provider = GetProvider(storageModeId);
        await operation(provider);
    }
}