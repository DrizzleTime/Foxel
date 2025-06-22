using Amazon.S3;
using Amazon.S3.Model;
using Amazon.S3.Transfer;
using Foxel.Services.Configuration;
using Microsoft.Extensions.Logging;

namespace Foxel.Services.Storage.Providers;

public class S3StorageConfig
{
    public string AccessKey { get; set; } = string.Empty;
    public string SecretKey { get; set; } = string.Empty;
    public string Endpoint { get; set; } = string.Empty;
    public string? Region { get; set; } // Region 可能为空，特别是对于非AWS S3兼容存储
    public bool UsePathStyleUrls { get; set; } = false;
    public string BucketName { get; set; } = string.Empty;
    public string? CdnUrl { get; set; }
}

[StorageProvider(StorageType.S3)]
public class S3StorageProvider : IStorageProvider
{
    private readonly S3StorageConfig _s3Config;
    private readonly IConfigService _configService; // 保留用于可能的应用级配置
    private readonly ILogger<S3StorageProvider> _logger;

    public S3StorageProvider(S3StorageConfig s3Config, IConfigService configService, ILogger<S3StorageProvider> logger)
    {
        _s3Config = s3Config;
        _configService = configService;
        _logger = logger;

        if (string.IsNullOrEmpty(_s3Config.AccessKey) ||
            string.IsNullOrEmpty(_s3Config.SecretKey) ||
            string.IsNullOrEmpty(_s3Config.Endpoint) ||
            string.IsNullOrEmpty(_s3Config.BucketName))
        {
            _logger.LogError("S3 Storage配置不完整 (AccessKey, SecretKey, Endpoint, BucketName 都是必需的).");
            throw new InvalidOperationException("S3 Storage配置不完整。");
        }
    }

    private AmazonS3Client CreateClient()
    {
        string accessKey = _s3Config.AccessKey;
        string secretKey = _s3Config.SecretKey;
        string endpoint = _s3Config.Endpoint;
        string? region = _s3Config.Region;
        bool usePathStyleUrls = _s3Config.UsePathStyleUrls;

        var config = new AmazonS3Config
        {
            ServiceURL = endpoint,
            UseHttp = !endpoint.StartsWith("https", StringComparison.OrdinalIgnoreCase),
            ForcePathStyle = usePathStyleUrls
        };

        if (!string.IsNullOrEmpty(region) && endpoint.Contains("amazonaws.com", StringComparison.OrdinalIgnoreCase))
        {
            config.RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(region);
        }
        
        return new AmazonS3Client(
            accessKey,
            secretKey,
            config
        );
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

            using var client = CreateClient();
            using var transferUtility = new TransferUtility(client);
            
            var uploadRequest = new TransferUtilityUploadRequest
            {
                InputStream = fileStream,
                Key = objectKey,
                BucketName = _s3Config.BucketName,
                ContentType = contentType
            };

            await transferUtility.UploadAsync(uploadRequest);
            
            // 返回文件的路径
            return objectKey;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "上传文件到S3时出错");
            throw;
        }
    }

    public async Task DeleteAsync(string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return;

            using var client = CreateClient();
            var deleteRequest = new DeleteObjectRequest
            {
                BucketName = _s3Config.BucketName,
                Key = storagePath
            };

            await client.DeleteObjectAsync(deleteRequest);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "从S3删除文件时出错");
        }
    }

    public string GetUrl(int pictureId,string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return "/images/unavailable.gif";

            string? cdnUrl = _s3Config.CdnUrl;

            // 如果配置了CDN URL，使用CDN
            if (!string.IsNullOrEmpty(cdnUrl))
            {
                return $"{cdnUrl.TrimEnd('/')}/{storagePath}";
            }

            // 否则使用S3直链或生成预签名URL
            using var client = CreateClient();
            var request = new GetPreSignedUrlRequest
            {
                BucketName = _s3Config.BucketName,
                Key = storagePath,
                Expires = DateTime.UtcNow.AddHours(1) // URL有效期1小时
            };

            return client.GetPreSignedURL(request);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "生成S3文件URL时出错");
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
            var tempDir = Path.Combine(Path.GetTempPath(), "FoxelS3Temp");
            if (!Directory.Exists(tempDir))
            {
                Directory.CreateDirectory(tempDir);
            }

            // 创建临时文件名
            string fileName = Path.GetFileName(storagePath);
            string tempFilePath = Path.Combine(tempDir, fileName);

            // 下载文件
            using var client = CreateClient();
            var request = new GetObjectRequest
            {
                BucketName = _s3Config.BucketName,
                Key = storagePath
            };

            using var response = await client.GetObjectAsync(request);
            await using var fileStream = new FileStream(tempFilePath, FileMode.Create);
            await response.ResponseStream.CopyToAsync(fileStream);

            return tempFilePath;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "从S3下载文件时出错");
            throw;
        }
    }
}
