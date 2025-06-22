using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using Foxel.Services.Configuration;
using System.Net;

namespace Foxel.Services.Storage.Providers;

public class TelegramStorageConfig
{
    public string BotToken { get; set; } = string.Empty;
    public string ChatId { get; set; } = string.Empty;
    public string? ProxyAddress { get; set; }
    public string? ProxyPort { get; set; }
    public string? ProxyUsername { get; set; }
    public string? ProxyPassword { get; set; }
}

[StorageProvider(StorageType.Telegram)]
public class TelegramStorageProvider(TelegramStorageConfig _telegramConfig, IConfigService configService, ILogger<TelegramStorageProvider> logger) : IStorageProvider
{
    public async Task<string> SaveAsync(Stream fileStream, string fileName, string contentType)
    {
        string botToken = _telegramConfig.BotToken;
        string chatId = _telegramConfig.ChatId;
        if (string.IsNullOrEmpty(botToken) || string.IsNullOrEmpty(chatId))
        {
            logger.LogError("Telegram BotToken 或 ChatId 未在配置中提供。");
            throw new InvalidOperationException("Telegram BotToken 或 ChatId 未配置。");
        }

        using var httpClient = CreateHttpClient();
        using var formData = new MultipartFormDataContent
        {
            { new StringContent(chatId), "chat_id" }
        };
        var safeFileName = Path.GetFileNameWithoutExtension(fileName);
        if (safeFileName.Length > 100)
            safeFileName = safeFileName.Substring(0, 100);
        formData.Add(new StringContent(safeFileName), "caption");

        using var memoryStream = new MemoryStream();
        await fileStream.CopyToAsync(memoryStream);
        memoryStream.Position = 0;

        var fileContent = new StreamContent(memoryStream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(contentType);

        formData.Add(fileContent, "document", fileName);

        try
        {
            var response =
                await httpClient.PostAsync($"https://api.telegram.org/bot{botToken}/sendDocument", formData);

            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                logger.LogError("Telegram API 请求失败: 状态码: {StatusCode}, 响应: {Response}", response.StatusCode, errorContent);
                throw new ApplicationException($"Telegram API 请求失败: {response.StatusCode}");
            }

            var responseContent = await response.Content.ReadAsStringAsync();
            var responseObj = JsonSerializer.Deserialize<TelegramResponse>(responseContent);
            if (responseObj == null || !responseObj.Ok)
            {
                throw new ApplicationException($"上传文件到 Telegram 失败: {responseContent}");
            }

            string fileId;
            string fileUniqueId;

            if (responseObj.Result?.Document != null)
            {
                fileId = responseObj.Result.Document.FileId;
                fileUniqueId = responseObj.Result.Document.FileUniqueId;
            }
            else if (responseObj.Result?.Sticker != null)
            {
                fileId = responseObj.Result.Sticker.FileId;
                fileUniqueId = responseObj.Result.Sticker.FileUniqueId;
            }
            else if (responseObj.Result?.Photo != null && responseObj.Result.Photo.Length > 0)
            {
                // 取最大尺寸的照片
                var largestPhoto = responseObj.Result.Photo.OrderByDescending(p => p.FileSize).First();
                fileId = largestPhoto.FileId;
                fileUniqueId = largestPhoto.FileUniqueId;
            }
            else
            {
                throw new ApplicationException($"无法从 Telegram 响应中提取文件信息: {responseContent}");
            }

            var metadata = new TelegramFileMetadata
            {
                FileId = fileId,
                FileUniqueId = fileUniqueId,
                MessageId = responseObj.Result.MessageId,
                ChatId = chatId,
                OriginalFileName = fileName,
                UploadDate = DateTime.UtcNow,
                MimeType = contentType
            };
            return JsonSerializer.Serialize(metadata);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "发送文件到 Telegram 时出错");
            throw;
        }
    }

    public async Task DeleteAsync(string storagePath)
    {
        try
        {
            var metadata = JsonSerializer.Deserialize<TelegramFileMetadata>(storagePath);
            if (metadata == null || string.IsNullOrEmpty(metadata.ChatId) || metadata.MessageId <= 0)
            {
                logger.LogWarning("无效的 Telegram 元数据，无法删除: {StoragePath}", storagePath);
                return;
            }

            string botToken = _telegramConfig.BotToken;
            if (string.IsNullOrEmpty(botToken))
            {
                logger.LogError("Telegram BotToken 未在配置中提供，无法删除文件。");
                return;
            }
            using var httpClient = CreateHttpClient();
            var url =
                $"https://api.telegram.org/bot{botToken}/deleteMessage?chat_id={metadata.ChatId}&message_id={metadata.MessageId}";
            var response = await httpClient.GetAsync(url);
            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                logger.LogWarning("删除 Telegram 消息失败: ChatId={ChatId}, MessageId={MessageId}, Status={StatusCode}, Response={ErrorContent}", metadata.ChatId, metadata.MessageId, response.StatusCode, errorContent);
            }
        }
        catch (JsonException jsonEx)
        {
            logger.LogWarning(jsonEx, "解析 Telegram 元数据以进行删除时出错: {StoragePath}", storagePath);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "删除 Telegram 文件时出错: {StoragePath}", storagePath);
        }
    }

    public string GetUrl(int pictureId,string storagePath)
    {
        try
        {
            var metadata = JsonSerializer.Deserialize<TelegramFileMetadata>(storagePath);
            if (metadata == null || string.IsNullOrEmpty(metadata.FileId))
            {
                throw new ApplicationException("无效的存储路径或元数据");
            }

            string serverUrl = configService["AppSettings:ServerUrl"];
            return $"{serverUrl}/api/picture/file/{pictureId}";
        }
        catch (JsonException jsonEx)
        {
            logger.LogError(jsonEx, "解析 Telegram 元数据以生成 URL 时出错: {StoragePath}", storagePath);
            return "/images/unavailable.gif";
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "生成 Telegram 文件 URL 时出错: {StoragePath}", storagePath);
            return "/images/unavailable.gif";
        }
    }

    /// <summary>
    /// 下载Telegram文件到临时目录
    /// </summary>
    /// <param name="storagePath">存储的元数据JSON</param>
    /// <returns>临时文件的完整路径</returns>
    public async Task<string> DownloadFileAsync(string storagePath)
    {
        try
        {
            var metadata = JsonSerializer.Deserialize<TelegramFileMetadata>(storagePath);
            if (metadata == null || string.IsNullOrEmpty(metadata.FileId))
            {
                throw new ApplicationException("无效的存储路径或元数据");
            }

            string botToken = _telegramConfig.BotToken;
            if (string.IsNullOrEmpty(botToken))
            {
                logger.LogError("Telegram BotToken 未在配置中提供，无法下载文件。");
                throw new InvalidOperationException("Telegram BotToken 未配置。");
            }

            using var httpClient = CreateHttpClient();
            var getFileUrl = $"https://api.telegram.org/bot{botToken}/getFile?file_id={metadata.FileId}";
            var getFileResponse = await httpClient.GetAsync(getFileUrl);

            if (!getFileResponse.IsSuccessStatusCode)
            {
                var errorContent = await getFileResponse.Content.ReadAsStringAsync();
                throw new ApplicationException($"获取 Telegram 文件路径失败: {getFileResponse.StatusCode}, {errorContent}");
            }

            var getFileContent = await getFileResponse.Content.ReadAsStringAsync();
            var getFileResult = JsonSerializer.Deserialize<TelegramGetFileResponse>(getFileContent);
            if (getFileResult == null || !getFileResult.Ok || string.IsNullOrEmpty(getFileResult.Result?.FilePath))
            {
                throw new ApplicationException("无法解析 Telegram 文件路径");
            }

            var filePath = getFileResult.Result.FilePath;
            var fileUrl = $"https://api.telegram.org/file/bot{botToken}/{filePath}";

            var fileResponse = await httpClient.GetAsync(fileUrl);
            if (!fileResponse.IsSuccessStatusCode)
            {
                throw new ApplicationException($"下载 Telegram 文件失败: {fileResponse.StatusCode}");
            }

            // 创建临时目录
            var tempDir = Path.Combine(Path.GetTempPath(), "FoxelTelegramTemp");
            if (!Directory.Exists(tempDir))
            {
                Directory.CreateDirectory(tempDir);
            }

            // 创建临时文件名 - 使用原始文件名或使用临时文件名
            string tempFileName = !string.IsNullOrEmpty(metadata.OriginalFileName)
                ? Path.GetFileName(metadata.OriginalFileName)
                : $"{Guid.NewGuid()}{Path.GetExtension(filePath)}";
            string tempFilePath = Path.Combine(tempDir, tempFileName);

            // 保存文件
            await using var fileStream = await fileResponse.Content.ReadAsStreamAsync();
            await using var outputStream = new FileStream(tempFilePath, FileMode.Create);
            await fileStream.CopyToAsync(outputStream);

            return tempFilePath;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "下载 Telegram 文件时出错");
            throw;
        }
    }

    /// <summary>
    /// 创建配置了代理的HttpClient
    /// </summary>
    /// <returns>已配置的HttpClient</returns>
    private HttpClient CreateHttpClient()
    {
        HttpClient client;

        // 检查是否有代理配置
        string? proxyAddress = _telegramConfig.ProxyAddress;
        string? proxyPort = _telegramConfig.ProxyPort;
        string? proxyUsername = _telegramConfig.ProxyUsername;
        string? proxyPassword = _telegramConfig.ProxyPassword;

        if (!string.IsNullOrEmpty(proxyAddress) && !string.IsNullOrEmpty(proxyPort) && int.TryParse(proxyPort, out int port))
        {
            var proxy = new WebProxy
            {
                Address = new Uri($"http://{proxyAddress}:{port}"),
                BypassProxyOnLocal = false,
                UseDefaultCredentials = false
            };

            // 如果提供了代理认证信息
            if (!string.IsNullOrEmpty(proxyUsername))
            {
                proxy.Credentials = new NetworkCredential(proxyUsername, proxyPassword);
            }

            var handler = new HttpClientHandler
            {
                Proxy = proxy,
                UseProxy = true
            };

            client = new HttpClient(handler);
        }
        else
        {
            client = new HttpClient();
        }

        // 设置超时
        client.Timeout = TimeSpan.FromMinutes(5);

        return client;
    }

    // 用于处理 Telegram API 响应的辅助类
    private class TelegramResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }

        [JsonPropertyName("result")] public TelegramResult? Result { get; set; }
    }

    private class TelegramResult
    {
        [JsonPropertyName("message_id")] public int MessageId { get; set; }

        [JsonPropertyName("document")] public TelegramDocument? Document { get; set; }

        [JsonPropertyName("sticker")] public TelegramSticker? Sticker { get; set; }

        [JsonPropertyName("photo")] public TelegramPhoto[]? Photo { get; set; }
    }

    private class TelegramDocument
    {
        [JsonPropertyName("file_id")] public string FileId { get; set; } = string.Empty;

        [JsonPropertyName("file_unique_id")] public string FileUniqueId { get; set; } = string.Empty;

        [JsonPropertyName("file_name")] public string? FileName { get; set; }

        [JsonPropertyName("mime_type")] public string? MimeType { get; set; }

        [JsonPropertyName("file_size")] public int FileSize { get; set; }
    }

    private class TelegramSticker
    {
        [JsonPropertyName("file_id")] public string FileId { get; set; } = string.Empty;

        [JsonPropertyName("file_unique_id")] public string FileUniqueId { get; set; } = string.Empty;

        [JsonPropertyName("width")] public int Width { get; set; }

        [JsonPropertyName("height")] public int Height { get; set; }

        [JsonPropertyName("file_size")] public int FileSize { get; set; }
    }

    private class TelegramPhoto
    {
        [JsonPropertyName("file_id")] public string FileId { get; set; } = string.Empty;

        [JsonPropertyName("file_unique_id")] public string FileUniqueId { get; set; } = string.Empty;

        [JsonPropertyName("width")] public int Width { get; set; }

        [JsonPropertyName("height")] public int Height { get; set; }

        [JsonPropertyName("file_size")] public int FileSize { get; set; }
    }
    // 存储关于上传文件的元数据
    private class TelegramFileMetadata
    {
        public string FileId { get; set; } = string.Empty;
        public string FileUniqueId { get; set; } = string.Empty;
        public int MessageId { get; set; }
        public string ChatId { get; set; } = string.Empty;
        public string OriginalFileName { get; set; } = string.Empty;
        public DateTime UploadDate { get; set; }
        public string? MimeType { get; set; }
    }

    private class TelegramGetFileResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }

        [JsonPropertyName("result")] public TelegramFileResult? Result { get; set; }
    }

    private class TelegramFileResult
    {
        [JsonPropertyName("file_path")] public string? FilePath { get; set; }
    }
}