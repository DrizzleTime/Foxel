using Foxel.Services.Configuration;
using Microsoft.Extensions.Logging;

namespace Foxel.Services.Storage.Providers;

public class LocalStorageConfig
{
    public string BasePath { get; set; } = string.Empty;

    public string ServerUrl { get; set; } = string.Empty;

    public string PublicBasePath { get; set; } = "/Uploads";
}

[StorageProvider(StorageType.Local)]
public class LocalStorageProvider : IStorageProvider
{
    private readonly LocalStorageConfig _config;
    private readonly ILogger<LocalStorageProvider> _logger;

    public LocalStorageProvider(LocalStorageConfig config, ILogger<LocalStorageProvider> logger)
    {
        _config = config;
        _logger = logger;
        if (string.IsNullOrWhiteSpace(_config.BasePath))
        {
            var defaultPath = Path.Combine(Directory.GetCurrentDirectory(), "DefaultUploads");
            _logger.LogWarning("LocalStorageConfig.BasePath 未配置，将使用默认路径: {DefaultPath}", defaultPath);
            throw new InvalidOperationException("LocalStorageConfig.BasePath 必须在配置中提供。");
        }

        Directory.CreateDirectory(_config.BasePath);
    }

    public async Task<string> SaveAsync(Stream fileStream, string fileName, string contentType)
    {
        try
        {
            string currentDate = DateTime.Now.ToString("yyyy/MM");
            string folder = Path.Combine(_config.BasePath, currentDate);
            Directory.CreateDirectory(folder);

            string newFileName = fileName;
            string filePath = Path.Combine(folder, newFileName);

            await using var output = new FileStream(filePath, FileMode.Create);
            await fileStream.CopyToAsync(output);
            return $"{_config.PublicBasePath.TrimEnd('/')}/{currentDate}/{newFileName}";
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "保存文件到本地存储时出错。BasePath: {BasePath}, FileName: {FileName}", _config.BasePath, fileName);
            throw;
        }
    }


    public Task DeleteAsync(string storagePath)
    {
        try
        {
            string relativePath = storagePath;
            if (!string.IsNullOrEmpty(_config.PublicBasePath) && storagePath.StartsWith(_config.PublicBasePath))
            {
                relativePath = storagePath.Substring(_config.PublicBasePath.Length);
            }

            string fullPath = Path.Combine(_config.BasePath, relativePath.TrimStart('/'));

            if (File.Exists(fullPath))
            {
                File.Delete(fullPath);
                _logger.LogInformation("已删除本地文件: {FullPath}", fullPath);
            }
            else
            {
                _logger.LogWarning("尝试删除本地文件但文件未找到: {FullPath}", fullPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "删除本地文件时出错。StoragePath: {StoragePath}, BasePath: {BasePath}", storagePath,
                _config.BasePath);
        }

        return Task.CompletedTask;
    }

    public string GetUrl(int pictureId,string? storagePath)
    {
        if (string.IsNullOrEmpty(storagePath))
            return $"/images/unavailable.gif";

        string serverUrl = _config.ServerUrl.TrimEnd('/');
        return string.IsNullOrEmpty(serverUrl) ? storagePath : $"{serverUrl}{storagePath}";
    }

    public Task<string> DownloadFileAsync(string storagePath)
    {
        try
        {
            string relativePath = storagePath;
            if (!string.IsNullOrEmpty(_config.PublicBasePath) && storagePath.StartsWith(_config.PublicBasePath))
            {
                relativePath = storagePath.Substring(_config.PublicBasePath.Length);
            }

            string fullPath = Path.Combine(_config.BasePath, relativePath.TrimStart('/'));

            if (!File.Exists(fullPath))
            {
                _logger.LogError("尝试下载但文件未找到: {FullPath}", fullPath);
                throw new FileNotFoundException($"本地存储中找不到文件: {fullPath}", fullPath);
            }

            string tempFileName = Path.GetRandomFileName();
            if (Path.HasExtension(fullPath))
            {
                tempFileName = Path.ChangeExtension(tempFileName, Path.GetExtension(fullPath));
            }

            string tempFilePath = Path.Combine(Path.GetTempPath(), tempFileName);

            File.Copy(fullPath, tempFilePath, true);
            _logger.LogInformation("已将文件 {FullPath} 复制到临时位置 {TempFilePath} 以供下载/处理", fullPath, tempFilePath);

            return Task.FromResult(tempFilePath); // 返回临时文件的路径
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "下载本地文件时出错。StoragePath: {StoragePath}, BasePath: {BasePath}", storagePath,
                _config.BasePath);
            throw;
        }
    }
}