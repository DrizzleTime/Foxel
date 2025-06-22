using System.Net.Http.Headers;
using System.Text;
using Foxel.Services.Configuration;

namespace Foxel.Services.Storage.Providers;

public class WebDavStorageConfig
{
    public string ServerUrl { get; set; } = string.Empty;
    public string BasePath { get; set; } = string.Empty;
    public string? UserName { get; set; }
    public string? Password { get; set; }
    public string? PublicUrl { get; set; }
}

[StorageProvider(StorageType.WebDAV)]
public class WebDavStorageProvider : IStorageProvider
{
    private readonly WebDavStorageConfig _webDavConfig;
    private readonly IConfigService _configService;
    private readonly ILogger<WebDavStorageProvider> _logger;

    public WebDavStorageProvider(WebDavStorageConfig webDavConfig, IConfigService configService, ILogger<WebDavStorageProvider> logger)
    {
        _webDavConfig = webDavConfig;
        _configService = configService;
        _logger = logger;

        if (string.IsNullOrEmpty(_webDavConfig.ServerUrl))
        {
            _logger.LogError("WebDAV Storage配置不完整 (ServerUrl 是必需的).");
            throw new InvalidOperationException("WebDAV Storage配置不完整。");
        }
    }

    private HttpClient CreateClient()
    {
        var httpClient = new HttpClient();
        var userName = _webDavConfig.UserName;
        var password = _webDavConfig.Password;

        if (!string.IsNullOrEmpty(userName) && !string.IsNullOrEmpty(password))
        {
            var authValue = Convert.ToBase64String(Encoding.ASCII.GetBytes($"{userName}:{password}"));
            httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", authValue);
        }

        return httpClient;
    }

    public async Task<string> SaveAsync(Stream fileStream, string fileName, string contentType)
    {
        try
        {
            string webDavServerUrl = _webDavConfig.ServerUrl.TrimEnd('/');
            string basePath = _webDavConfig.BasePath?.Trim('/') ?? string.Empty;

            // 创建唯一的文件存储路径
            string currentDate = DateTime.Now.ToString("yyyy/MM");
            // fileName 参数现在是期望的最终文件名部分，例如 "guid.ext"
            // string ext = Path.GetExtension(fileName); // 旧的 fileName 是原始文件名，现在 fileName 是目标文件名
            // string newFileName = $"{Guid.NewGuid()}{ext}"; // 旧逻辑
            string newFileName = fileName; // 新逻辑
            string relativePath = $"{basePath}/{currentDate}/{newFileName}";

            // 确保目录存在
            await EnsureDirectoryExistsAsync($"{basePath}/{currentDate}");

            // 上传文件内容
            var requestUri = $"{webDavServerUrl}/{relativePath}";
            using var client = CreateClient();
            using var content = new StreamContent(fileStream);
            content.Headers.ContentType = new MediaTypeHeaderValue(contentType);

            using var request = new HttpRequestMessage(HttpMethod.Put, requestUri);
            request.Content = content;

            var response = await client.SendAsync(request);
            response.EnsureSuccessStatusCode();

            return relativePath;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "上传文件到WebDAV时出错");
            throw;
        }
    }

    public async Task DeleteAsync(string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return;

            string webDavServerUrl = _webDavConfig.ServerUrl.TrimEnd('/');
            var requestUri = $"{webDavServerUrl}/{storagePath}";

            using var client = CreateClient();
            var response = await client.DeleteAsync(requestUri);

            if (response.StatusCode != System.Net.HttpStatusCode.NotFound)
            {
                response.EnsureSuccessStatusCode();
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "从WebDAV删除文件时出错");
        }
    }

    public string GetUrl(int pictureId,string storagePath)
    {
        try
        {
            if (string.IsNullOrEmpty(storagePath))
                return "/images/unavailable.gif";

            string? publicUrl = _webDavConfig.PublicUrl?.TrimEnd('/');
            string serverUrl = _configService["AppSettings:ServerUrl"]; 

            if (!string.IsNullOrEmpty(publicUrl))
            {
                return $"{publicUrl}/{storagePath}";
            }

            return $"{serverUrl}/api/picture/file/{pictureId}";
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "生成WebDAV文件URL时出错");
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

            string webDavServerUrl = _webDavConfig.ServerUrl.TrimEnd('/');

            // 创建临时目录
            var tempDir = Path.Combine(Path.GetTempPath(), "FoxelWebDAVTemp");
            if (!Directory.Exists(tempDir))
            {
                Directory.CreateDirectory(tempDir);
            }

            // 创建临时文件名
            string fileName = Path.GetFileName(storagePath);
            string tempFilePath = Path.Combine(tempDir, fileName);

            // 下载文件
            var requestUri = $"{webDavServerUrl}/{storagePath}";
            using var client = CreateClient();
            using var request = new HttpRequestMessage(HttpMethod.Get, requestUri);
            var response = await client.SendAsync(request);
            response.EnsureSuccessStatusCode();

            await using var fileStream = new FileStream(tempFilePath, FileMode.Create);
            await response.Content.CopyToAsync(fileStream);

            return tempFilePath;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "从WebDAV下载文件时出错");
            throw;
        }
    }

    /// <summary>
    /// 确保WebDAV上的目录存在
    /// </summary>
    private async Task EnsureDirectoryExistsAsync(string directoryPath)
    {
        try
        {
            string webDavServerUrl = _webDavConfig.ServerUrl.TrimEnd('/');
            var requestUri = $"{webDavServerUrl}/{directoryPath}";
            using var client = CreateClient();

            // 检查目录是否存在 - 使用新的请求对象
            using var headRequest = new HttpRequestMessage(HttpMethod.Head, requestUri);
            var response = await client.SendAsync(headRequest);

            if (response.IsSuccessStatusCode)
                return;

            // 创建目录 - 使用新的请求对象
            using var mkcolRequest = new HttpRequestMessage(new HttpMethod("MKCOL"), requestUri);
            response = await client.SendAsync(mkcolRequest);

            // 处理状态码
            if (response.StatusCode == System.Net.HttpStatusCode.Conflict ||
                response.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                // 递归创建父目录
                var parentPath = Path.GetDirectoryName(directoryPath.TrimEnd('/'))?.Replace('\\', '/');
                if (!string.IsNullOrEmpty(parentPath))
                {
                    await EnsureDirectoryExistsAsync(parentPath);

                    using var retryRequest = new HttpRequestMessage(new HttpMethod("MKCOL"), requestUri);
                    response = await client.SendAsync(retryRequest);

                    if (response.StatusCode == System.Net.HttpStatusCode.MethodNotAllowed)
                    {
                        using var putRequest = new HttpRequestMessage(HttpMethod.Put, $"{requestUri}/.dummy");
                        putRequest.Content = new StringContent(string.Empty);
                        await client.SendAsync(putRequest);
                    }
                    else
                    {
                        response.EnsureSuccessStatusCode();
                    }
                }
            }
            else if (response.StatusCode == System.Net.HttpStatusCode.MethodNotAllowed)
            {
                using var putRequest = new HttpRequestMessage(HttpMethod.Put, $"{requestUri}/.dummy");
                putRequest.Content = new StringContent(string.Empty);
                var putResponse = await client.SendAsync(putRequest);
                putResponse.EnsureSuccessStatusCode();
            }
            else
            {
                response.EnsureSuccessStatusCode();
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "确保WebDAV目录存在时出错");
            throw;
        }
    }
}