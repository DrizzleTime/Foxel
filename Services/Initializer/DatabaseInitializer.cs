using Foxel.Models.DataBase;
using Foxel.Services.Configuration;
using Foxel.Services.Logging;
using Foxel.Services.Storage;
using Microsoft.EntityFrameworkCore;

namespace Foxel.Services.Initializer;

public class DatabaseInitializer(
    IDbContextFactory<MyDbContext> contextFactory,
    IConfigService configService,
    ILogger<DatabaseInitializer> logger)
    : IDatabaseInitializer
{
    private const string InitializationFlag = "System:InitializationCompleted";

    public async Task InitializeAsync()
    {
        // 在初始化期间禁用数据库日志记录
        DatabaseLogger.SetDatabaseReady(false);

        logger.LogInformation("开始检查数据库初始化状态...");

        // 执行数据库迁移
        await MigrateDatabaseAsync();

        // 检查是否已经完成初始化
        if (await configService.ExistsAsync(InitializationFlag) &&
            configService[InitializationFlag] == "true")
        {
            logger.LogInformation("数据库已完成初始化，跳过初始化步骤");
            DatabaseLogger.SetDatabaseReady(true);
            return;
        }

        logger.LogInformation("开始初始化数据库配置...");

        await using var context = await contextFactory.CreateDbContextAsync();

        // 确保数据库已创建
        await context.Database.EnsureCreatedAsync();

        // 初始化默认配置
        var defaultConfigs = new Dictionary<string, string>
        {
            // JWT配置
            ["Jwt:SecretKey"] = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N"),
            ["Jwt:Issuer"] = "Foxel",
            ["Jwt:Audience"] = "FoxelUsers",

            // GitHub认证配置
            ["Authentication:GitHubClientId"] = "placeholder_replace_with_actual_github_client_id",
            ["Authentication:GitHubClientSecret"] = "placeholder_replace_with_actual_github_client_secret",
            ["Authentication:GitHubCallbackUrl"] = "",

            // AI相关配置
            ["AI:ApiEndpoint"] = "",
            ["AI:ApiKey"] = "",
            ["AI:Model"] = "",
            ["AI:EmbeddingModel"] = "",
            ["AI:ImageAnalysisPrompt"] =
                "Please analyze the given image in detail and provide a comprehensive description suitable for **vector embedding** and **text-based image retrieval**. Your description must include the following key elements:\n\n- **Main subject**\n- **Scene environment**\n- **Color characteristics**\n- **Composition layout**\n- **Stylistic features**\n- **Emotional atmosphere**\n- **Fine-grained details**\n\nReturn your response in **valid JSON format** as shown below:\n\n```json\n{\n  \"title\": \"用中文简要概括图像核心内容的标题\",\n  \"description\": \"使用中文全面、详细地描述图像内容，涵盖上述所有要素。使用丰富且精确的词汇，避免模糊或通用的表述。描述不得超过2000个字符。\"\n}\n```\n\n⚠️ Make sure:\n- Both `title` and `description` must be written in **Chinese**.\n- The `description` must be **rich, accurate**, and **strictly under 2000 characters**.\n- The output must be **valid JSON only**, with no code fences or extra formatting.",
            ["AI:TagGenerationPrompt"] =
                "Please generate **5 most relevant tags** for the given image. Each tag should be a **short and descriptive** word or phrase that accurately reflects key visual or thematic elements of the image.\n\nReturn your response in **valid JSON format** as shown below:\n\n```json\n{\n  \"tags\": [\"标签1\", \"标签2\", \"标签3\", \"标签4\", \"标签5\"]\n}\n```\n\nMake sure the output is **strictly valid JSON**.",
            ["AI:TagMatchingPrompt"] =
                "Given a list of tags: `[{tagsText}]`\n\nPlease strictly select only those tags that are **highly relevant** to the following description (select **up to 5**). Only include tags that **exactly or strongly match** the content. If **none** of the tags are a good match, return an **empty array** instead of including loosely related ones.\n\n**Description:**\n{description}\n\nReturn your response in **valid JSON format** as shown below:\n\n```json\n{\n  \"tags\": [\"标签1\", \"标签2\", \"标签3\", \"标签4\", \"标签5\"]\n}\n```\n\n⚠️ Do **not** include code fences (no triple backticks), and ensure the JSON is **valid** and includes only truly matching tag names.",

            // 上传配置
            ["Upload:HighQualityImageCompressionQuality"] = "85",
            ["Upload:ThumbnailMaxWidth"] = "500",
            ["Upload:ThumbnailCompressionQuality"] = "75",

            // 其他配置
            ["Storage:DefaultStorageModeId"] = "1",
            ["AppSettings:ServerUrl"] = "",
            ["AppSettings:EnableRegistration"] = "true",
            ["AppSettings:EnableAnonymousImageHosting"] = "true",
            ["VectorDb:Type"] = "InMemory"
        };

        foreach (var (key, value) in defaultConfigs)
        {
            await EnsureConfigExistsAsync(key, value);
        }

        // 确保向量数据库配置存在
        if (!await configService.ExistsAsync("VectorDb:Type"))
        {
            await configService.SetConfigAsync("VectorDb:Type", "InMemory", "向量数据库类型");
        }

        // 初始化管理员角色和用户
        await InitializeAdminRoleAndUserAsync();

        // 初始化默认存储模式
        await InitializeDefaultStorageModeAsync();

        // 标记初始化已完成
        await configService.SetConfigAsync(InitializationFlag, "true", "系统初始化完成标志");

        logger.LogInformation("数据库配置初始化完成");

        // 初始化完成后启用数据库日志记录
        DatabaseLogger.SetDatabaseReady(true);
    }

    private async Task MigrateDatabaseAsync()
    {
        logger.LogInformation("开始执行数据库迁移...");
        try
        {
            await using var context = await contextFactory.CreateDbContextAsync();
            await context.Database.MigrateAsync();
            logger.LogInformation("数据库迁移完成");
        }
        catch (Exception ex)
        {
            logger.LogWarning("数据库迁移过程中出现警告或错误: {Error}", ex.Message);
            logger.LogInformation("尝试确保数据库已创建...");
            await using var context = await contextFactory.CreateDbContextAsync();
            await context.Database.EnsureCreatedAsync();
        }
    }

    private async Task EnsureConfigExistsAsync(string key, string value)
    {
        if (!await configService.ExistsAsync(key))
        {
            logger.LogInformation("创建配置项: {Key}", key);
            await configService.SetConfigAsync(key, value, $"自动创建的{key}配置");
        }
    }

    private async Task InitializeAdminRoleAndUserAsync()
    {
        await using var context = await contextFactory.CreateDbContextAsync();

        // 检查并创建管理员角色
        var adminRole = await context.Roles.FirstOrDefaultAsync(r => r.Name == "Administrator");
        if (adminRole == null)
        {
            logger.LogInformation("创建管理员角色");
            adminRole = new Role
            {
                Name = "Administrator",
                Description = "系统管理员角色",
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow
            };
            await context.Roles.AddAsync(adminRole);
            await context.SaveChangesAsync();
        }

        // 检查并创建用户角色
        var userRole = await context.Roles.FirstOrDefaultAsync(r => r.Name == "User");
        if (userRole == null)
        {
            logger.LogInformation("创建用户角色");
            userRole = new Role
            {
                Name = "User",
                Description = "普通用户角色",
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow
            };
            await context.Roles.AddAsync(userRole);
            await context.SaveChangesAsync();
        }

        logger.LogInformation("请注意，第一个注册的用户将自动成为管理员");
    }

    private async Task InitializeDefaultStorageModeAsync()
    {
        await using var context = await contextFactory.CreateDbContextAsync();

        const string defaultStorageModeName = "本地数据";
        if (!await context.StorageModes.AnyAsync(sm => sm.Name == defaultStorageModeName))
        {
            logger.LogInformation("创建默认本地存储模式: {StorageModeName}", defaultStorageModeName);
            var localDefaultStorageMode = new StorageMode
            {
                Name = defaultStorageModeName,
                IsEnabled = true,
                StorageType = StorageType.Local,
                ConfigurationJson =
                    "{\"BasePath\": \"/app/Uploads\", \"ServerUrl\": \"\", \"PublicBasePath\": \"/Uploads\"}",
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow
            };
            await context.StorageModes.AddAsync(localDefaultStorageMode);
            await context.SaveChangesAsync();
            logger.LogInformation("默认本地存储模式创建成功");
        }
        else
        {
            logger.LogInformation("默认本地存储模式 '{StorageModeName}' 已存在，跳过创建。", defaultStorageModeName);
        }
    }
}