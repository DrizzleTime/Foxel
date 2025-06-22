using COSXML;
using COSXML.Auth;
using COSXML.CosException;
using COSXML.Model.Object;
using COSXML.Model.Tag;
using COSXML.Transfer;
using Foxel.Services.Configuration;
using Microsoft.Extensions.Logging;

namespace Foxel.Services.Storage.Providers;

public class CosStorageConfig
{
    public string Region { get; set; } = string.Empty;
    public string SecretId { get; set; } = string.Empty;
    public string SecretKey { get; set; } = string.Empty;
    public string? Token { get; set; } // Token 可能为空
    public string BucketName { get; set; } = string.Empty;
    public string? CdnUrl { get; set; }
    public bool PublicRead { get; set; } = false;
}

public class CustomQCloudCredentialProvider : DefaultSessionQCloudCredentialProvider
{
    private readonly CosStorageConfig _config;
    private readonly ILogger<CustomQCloudCredentialProvider> _logger;

    public CustomQCloudCredentialProvider(CosStorageConfig config, ILogger<CustomQCloudCredentialProvider> logger) 
        : base(null, null, 0L, null) // Base constructor parameters are set in Refresh
    {
        _config = config;
        _logger = logger;
        Refresh();
    }

    public sealed override void Refresh()
    {
        try
        {
            string tmpSecretId = _config.SecretId;
            string tmpSecretKey = _config.SecretKey;
            string? tmpToken = _config.Token; 
            long tmpStartTime = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            // 腾讯云建议临时密钥有效期最长2小时（7200秒）
            long tmpExpiredTime = tmpStartTime + 7200; 
            SetQCloudCredential(tmpSecretId, tmpSecretKey,
                $"{tmpStartTime};{tmpExpiredTime}", tmpToken);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "刷新临时密钥时出错");
            throw;
        }
    }
}

[StorageProvider(StorageType.Cos)]
public class CosStorageProvider : IStorageProvider
{
    private readonly CosStorageConfig _cosConfig;
    private readonly IConfigService _configService; // 保留用于可能的应用级配置
    private readonly ILogger<CosStorageProvider> _logger;

    public CosStorageProvider(CosStorageConfig cosConfig, IConfigService configService, ILogger<CosStorageProvider> logger)
    {
        _cosConfig = cosConfig;
        _configService = configService; // 存储起来以备后用
        _logger = logger;

        if (string.IsNullOrEmpty(_cosConfig.Region) ||
            string.IsNullOrEmpty(_cosConfig.SecretId) ||
            string.IsNullOrEmpty(_cosConfig.SecretKey) ||
            string.IsNullOrEmpty(_cosConfig.BucketName))
        {
            _logger.LogError("COS Storage配置不完整 (Region, SecretId, SecretKey, BucketName 都是必需的).");
            throw new InvalidOperationException("COS Storage配置不完整。");
        }
    }

    private CosXml CreateClient()
    {
        var config = new CosXmlConfig.Builder()
            .IsHttps(true) 
            .SetRegion(_cosConfig.Region)
            .SetDebugLog(true) 
            .Build();
            
        var cosCredentialProvider = new CustomQCloudCredentialProvider(_cosConfig, 
            _logger.IsEnabled(LogLevel.Debug) ? 
                Microsoft.Extensions.Logging.LoggerFactory.Create(builder => builder.AddConsole()).CreateLogger<CustomQCloudCredentialProvider>() :
                Microsoft.Extensions.Logging.Abstractions.NullLogger<CustomQCloudCredentialProvider>.Instance);
        
        return new CosXmlServer(config, cosCredentialProvider);
    }

    public async Task<string> SaveAsync(Stream fileStream, string fileName, string contentType)
    {
        try
        {
            // 创建唯一的文件存储路径
            string currentDate = DateTime.Now.ToString("yyyy/MM");
            // fileName 参数现在是期望的最终文件名部分，例如 "guid.ext"
            // string ext = Path.GetExtension(fileName); // 旧的 fileName 是原始文件名，现在 fileName 是目标文件名
            // string objectKey = $"{currentDate}/{Guid.NewGuid()}{ext}"; // 旧逻辑
            string objectKey = $"{currentDate}/{fileName}"; // 新逻辑

            // 创建临时文件
            string tempPath = Path.GetTempFileName();
            try
            {
                await using (var fileStream2 = new FileStream(tempPath, FileMode.Create))
                {
                    await fileStream.CopyToAsync(fileStream2);
                }

                var cosXmlClient = CreateClient();
                var transferConfig = new TransferConfig();
                var transferManager = new TransferManager(cosXmlClient, transferConfig);
                var uploadTask = new COSXMLUploadTask(_cosConfig.BucketName, objectKey);
                uploadTask.SetSrcPath(tempPath);
                await transferManager.UploadAsync(uploadTask);
                return objectKey;
            }
            finally
            {
                // 确保临时文件被删除
                if (File.Exists(tempPath))
                {
                    File.Delete(tempPath);
                }
            }
        }
        catch (CosClientException clientEx)
        {
            _logger.LogError(clientEx, "COS客户端异常");
            throw;
        }
        catch (CosServerException serverEx)
        {
            _logger.LogError(serverEx, "COS服务器异常: {ServerInfo}", serverEx.GetInfo());
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "上传文件到腾讯云COS时出错");
            throw;
        }
    }

    public async Task DeleteAsync(string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return;

            var cosXmlClient = CreateClient();
            var request = new DeleteObjectRequest(_cosConfig.BucketName, storagePath);
            await Task.Run(() => cosXmlClient.DeleteObject(request));
        }
        catch (CosClientException clientEx)
        {
            _logger.LogWarning(clientEx, "COS客户端异常");
        }
        catch (CosServerException serverEx)
        {
            _logger.LogWarning(serverEx, "COS服务器异常: {ServerInfo}", serverEx.GetInfo());
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "从腾讯云COS删除文件时出错");
        }
    }

    public string GetUrl(int pictureId,string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return "/images/unavailable.gif";

            string? cdnUrl = _cosConfig.CdnUrl;
            string bucketName = _cosConfig.BucketName;
            string region = _cosConfig.Region;
            bool isPublicRead = _cosConfig.PublicRead;

            // 优先使用CDN
            if (!string.IsNullOrEmpty(cdnUrl))
                return $"{cdnUrl.TrimEnd('/')}/{storagePath}";

            // 公开读取的桶可直接访问
            if (isPublicRead)
                return $"https://{bucketName}.cos.{region}.myqcloud.com/{storagePath}";

            var cosXmlClient = CreateClient();
            var bucketParts = bucketName.Split('-');
            var request = new PreSignatureStruct
            {
                bucket = bucketParts[0],
                appid = bucketParts[1],
                region = region,
                key = storagePath,
                httpMethod = "GET",
                isHttps = true,
                signDurationSecond = 3600 * 24  
            };
            
            var url = cosXmlClient.GenerateSignURL(request);
            return url;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "生成腾讯云COS文件URL时出错");
            return "/images/unavailable.gif";
        }
    }

    public async Task<string> DownloadFileAsync(string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
            {
                throw new ArgumentException("存储路径不能为空");
            }

            // 创建临时目录
            var tempDir = Path.Combine(Path.GetTempPath(), "FoxelCosTemp");
            if (!Directory.Exists(tempDir))
            {
                Directory.CreateDirectory(tempDir);
            }

            string bucketName = _cosConfig.BucketName;
            string fileName = Path.GetFileName(storagePath);
            
            var cosXmlClient = CreateClient();
            var transferConfig = new TransferConfig();
            var transferManager = new TransferManager(cosXmlClient, transferConfig);
            var downloadTask = new COSXMLDownloadTask(bucketName, storagePath, tempDir, fileName);
            await transferManager.DownloadAsync(downloadTask);
            return Path.Combine(tempDir, fileName);
        }
        catch (CosClientException clientEx)
        {
            _logger.LogError(clientEx, "COS客户端异常");
            throw;
        }
        catch (CosServerException serverEx)
        {
            _logger.LogError(serverEx, "COS服务器异常: {ServerInfo}", serverEx.GetInfo());
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "从腾讯云COS下载文件时出错");
            throw;
        }
    }
}
