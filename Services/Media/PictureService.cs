using System.Text.Json;
using Foxel.Models;
using Foxel.Models.DataBase;
using Foxel.Models.Enums;
using Foxel.Models.Response.Picture;
using Foxel.Services.AI;
using Foxel.Services.Background;
using Foxel.Services.Configuration;
using Foxel.Services.Storage;
using Foxel.Services.Mapping;
using Foxel.Services.VectorDb;
using Foxel.Utils;
using Microsoft.EntityFrameworkCore;

namespace Foxel.Services.Media;

public class PictureService(
    IDbContextFactory<MyDbContext> contextFactory,
    IAiService embeddingService,
    IConfigService configuration,
    IBackgroundTaskQueue backgroundTaskQueue,
    IVectorDbService vectorDbService,
    IStorageService storageService,
    IMappingService mappingService, // 添加 IMappingService
    ILogger<PictureService> logger)
    : IPictureService
{

    public async Task<PaginatedResult<PictureResponse>> GetPicturesAsync(
        int page = 1,
        int pageSize = 8,
        string? searchQuery = null,
        List<string>? tags = null,
        DateTime? startDate = null,
        DateTime? endDate = null,
        int? userId = null,
        string? sortBy = "newest",
        bool? onlyWithGps = false,
        bool useVectorSearch = false,
        double similarityThreshold = 0.36,
        int? excludeAlbumId = null,
        int? albumId = null,
        bool onlyFavorites = false,
        int? ownerId = null,
        bool includeAllPublic = false
    )
    {
        if (page < 1) page = 1;
        if (pageSize < 1) pageSize = 8;

        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 决定是使用向量搜索还是普通搜索
        if (useVectorSearch && !string.IsNullOrWhiteSpace(searchQuery))
        {
            try
            {
                return await PerformVectorSearchAsync(
                    dbContext, page, pageSize, searchQuery, tags,
                    startDate, endDate, userId, onlyWithGps, similarityThreshold,
                    excludeAlbumId, albumId, onlyFavorites, ownerId, includeAllPublic);
            }
            catch (Exception ex)
            {
                // 如果向量搜索失败，记录错误并回退到标准搜索
                logger.LogWarning("向量搜索失败，回退到标准搜索: {Message}", ex.Message);

                // 如果是明确的配置错误，则向上抛出异常
                if (ex.Message.Contains("请检查嵌入模型配置"))
                {
                    throw;
                }
            }
        }

        return await PerformStandardSearchAsync(
            dbContext, page, pageSize, searchQuery, tags,
            startDate, endDate, userId, sortBy, onlyWithGps,
            excludeAlbumId, albumId, onlyFavorites, ownerId, includeAllPublic);
    }

    // 执行向量搜索
    private async Task<PaginatedResult<PictureResponse>> PerformVectorSearchAsync(
        MyDbContext dbContext,
        int page,
        int pageSize,
        string searchQuery,
        List<string>? tags,
        DateTime? startDate,
        DateTime? endDate,
        int? userId,
        bool? onlyWithGps,
        double similarityThreshold,
        int? excludeAlbumId,
        int? albumId,
        bool onlyFavorites,
        int? ownerId,
        bool includeAllPublic)
    {
        var queryEmbedding = await embeddingService.GetEmbeddingAsync(searchQuery);
        var res = await vectorDbService.SearchAsync(queryEmbedding, userId);

        var ids = res.Select(r => r.Id).ToList();
        var picturesData = await dbContext.Pictures
            .Include(p => p.Tags)
            .Include(p => p.User)
            .Include(p => p.StorageMode)
            .Where(p => ids.Contains((ulong)p.Id))
            .ToListAsync();
        var picturesOrdered = ids
            .Select(id => picturesData.FirstOrDefault(p => p.Id == (int)id))
            .Where(p => p != null)
            .ToList();
        var paginatedResults = picturesOrdered
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(p => mappingService.MapPictureToResponse(p!))
            .ToList();


        var totalCount = picturesOrdered.Count;

        await PopulateFavoriteInfo(dbContext, paginatedResults, userId);

        if (userId.HasValue)
        {
            await PopulateAlbumInfo(dbContext, paginatedResults, userId.Value);
        }

        return new PaginatedResult<PictureResponse>
        {
            Data = paginatedResults,
            Page = page,
            PageSize = pageSize,
            TotalCount = totalCount
        };
    }

    // 执行标准搜索
    private async Task<PaginatedResult<PictureResponse>> PerformStandardSearchAsync(
        MyDbContext dbContext,
        int page,
        int pageSize,
        string? searchQuery,
        List<string>? tags,
        DateTime? startDate,
        DateTime? endDate,
        int? userId,
        string? sortBy,
        bool? onlyWithGps,
        int? excludeAlbumId,
        int? albumId,
        bool onlyFavorites,
        int? ownerId,
        bool includeAllPublic)
    {
        // 构建基础查询
        IQueryable<Picture> query = dbContext.Pictures
            .Include(p => p.Tags)
            .Include(p => p.User)
            .Include(p => p.Faces!)
            .ThenInclude(f => f.Cluster);

        // 应用文本搜索条件
        if (!string.IsNullOrWhiteSpace(searchQuery))
        {
            var searchTerm = searchQuery.ToLower();
            query = query.Where(p =>
                p.Name.ToLower().Contains(searchTerm) ||
                p.Description.ToLower().Contains(searchTerm));
        }

        // 应用共通的查询条件
        query = ApplyCommonFilters(query, tags, startDate, endDate, userId, onlyWithGps,
            excludeAlbumId, albumId, onlyFavorites, ownerId, includeAllPublic);

        // 应用排序
        query = ApplySorting(query, sortBy);

        // 获取总记录数
        var totalCount = await query.CountAsync();

        // 获取分页数据
        var picturesData = await query
            .Include(x => x.StorageMode)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync();

        // 转换为响应格式
        var pictures = picturesData
            .Select(p => mappingService.MapPictureToResponse(p))
            .ToList();

        // 处理收藏信息
        await PopulateFavoriteInfo(dbContext, pictures, userId);

        // 为当前用户的图片添加相册信息
        if (userId.HasValue)
        {
            await PopulateAlbumInfo(dbContext, pictures, userId.Value);
        }

        return new PaginatedResult<PictureResponse>
        {
            Data = pictures,
            Page = page,
            PageSize = pageSize,
            TotalCount = totalCount
        };
    }

    // 应用共通的过滤条件
    private IQueryable<Picture> ApplyCommonFilters(
        IQueryable<Picture> query,
        List<string>? tags,
        DateTime? startDate,
        DateTime? endDate,
        int? userId,
        bool? onlyWithGps,
        int? excludeAlbumId,
        int? albumId,
        bool onlyFavorites,
        int? ownerId,
        bool includeAllPublic)
    {
        // 应用标签筛选
        if (tags != null && tags.Any())
        {
            foreach (var tag in tags)
            {
                var tagName = tag.Trim();
                if (!string.IsNullOrEmpty(tagName))
                {
                    var normalizedTagName = tagName.ToLower();
                    query = query.Where(p => p.Tags!.Any(t => t.Name.ToLower().Equals(normalizedTagName)));
                }
            }
        }

        // 应用日期范围筛选
        if (startDate.HasValue)
        {
            DateTime utcStartDate = startDate.Value.ToUniversalTime();
            query = query.Where(p =>
                (p.TakenAt.HasValue && p.TakenAt >= utcStartDate) ||
                (!p.TakenAt.HasValue && p.CreatedAt >= utcStartDate));
        }

        if (endDate.HasValue)
        {
            DateTime utcEndDate = endDate.Value.ToUniversalTime().AddDays(1).AddMilliseconds(-1);
            query = query.Where(p =>
                (p.TakenAt.HasValue && p.TakenAt <= utcEndDate) ||
                (!p.TakenAt.HasValue && p.CreatedAt <= utcEndDate));
        }

        // 应用用户筛选和权限过滤逻辑
        if (ownerId.HasValue)
        {
            if (userId.HasValue && userId.Value == ownerId.Value)
            {
                query = query.Where(p => p.User != null && p.User.Id == ownerId.Value);
            }
            else
            {
                query = query.Where(p =>
                    p.User != null && p.User.Id == ownerId.Value && p.Permission == PermissionType.Public);
            }
        }
        else if (userId.HasValue)
        {
            if (includeAllPublic)
            {
                query = query.Where(p =>
                    (p.User != null && p.User.Id == userId.Value) ||
                    (p.User != null && p.User.Id != userId.Value &&
                     p.Permission == PermissionType.Public)
                );
            }
            else
            {
                query = query.Where(p => p.User != null && p.User.Id == userId.Value);
            }
        }
        else
        {
            query = query.Where(p => p.Permission == PermissionType.Public);
        }

        // 筛选有GPS信息的图片
        if (onlyWithGps == true)
        {
            query = query.Where(p =>
                p.ExifInfo != null &&
                !string.IsNullOrEmpty(p.ExifInfo.GpsLatitude) &&
                !string.IsNullOrEmpty(p.ExifInfo.GpsLongitude));
        }

        // 排除指定相册的图片
        if (excludeAlbumId.HasValue)
        {
            query = query.Where(p => p.AlbumId != excludeAlbumId.Value || p.AlbumId == null);
        }

        // 筛选指定相册的图片
        if (albumId.HasValue)
        {
            query = query.Where(p => p.AlbumId == albumId.Value);
        }

        // 筛选收藏的图片
        if (onlyFavorites && userId.HasValue)
        {
            query = query.Where(p => p.Favorites!.Any(f => f.User.Id == userId.Value));
        }

        return query;
    }

    // 应用排序
    private IQueryable<Picture> ApplySorting(IQueryable<Picture> query, string? sortBy)
    {
        return sortBy?.ToLower() switch
        {
            // 拍摄时间排序
            "takenat_desc" or "newest" => query.OrderByDescending(p => p.TakenAt ?? p.CreatedAt),
            "takenat_asc" or "oldest" => query.OrderBy(p => p.TakenAt ?? p.CreatedAt),

            // 上传时间排序
            "uploaddate_desc" => query.OrderByDescending(p => p.CreatedAt),
            "uploaddate_asc" => query.OrderBy(p => p.CreatedAt),

            // 名称排序
            "name_asc" or "name" => query.OrderBy(p => p.Name),
            "name_desc" => query.OrderByDescending(p => p.Name),

            // 默认排序
            _ => query.OrderByDescending(p => p.TakenAt ?? p.CreatedAt)
        };
    }

    // 填充收藏信息
    private async Task PopulateFavoriteInfo(MyDbContext dbContext, List<PictureResponse> pictures, int? userId)
    {
        if (userId.HasValue && pictures.Any())
        {
            var pictureIds = pictures.Select(p => p.Id).ToList();

            // 获取用户收藏的图片ID
            var favoritedPictureIds = await dbContext.Favorites
                .Where(f => f.User.Id == userId.Value && pictureIds.Contains(f.PictureId))
                .Select(f => f.PictureId)
                .ToHashSetAsync(); // 使用 ToHashSetAsync 提高查找效率

            // 一次性获取所有相关图片的收藏总数
            var favoriteCounts = await dbContext.Favorites
                .Where(f => pictureIds.Contains(f.PictureId))
                .GroupBy(f => f.PictureId)
                .Select(g => new { PictureId = g.Key, Count = g.Count() })
                .ToDictionaryAsync(x => x.PictureId, x => x.Count);

            foreach (var picture in pictures)
            {
                picture.IsFavorited = favoritedPictureIds.Contains(picture.Id);
                picture.FavoriteCount = favoriteCounts.GetValueOrDefault(picture.Id, 0);
            }
        }
        else if (pictures.Any()) // 如果用户未登录，仍然需要获取收藏总数
        {
            var pictureIds = pictures.Select(p => p.Id).ToList();
            var favoriteCounts = await dbContext.Favorites
                .Where(f => pictureIds.Contains(f.PictureId))
                .GroupBy(f => f.PictureId)
                .Select(g => new { PictureId = g.Key, Count = g.Count() })
                .ToDictionaryAsync(x => x.PictureId, x => x.Count);

            foreach (var picture in pictures)
            {
                picture.IsFavorited = false; // 用户未登录，不可能收藏
                picture.FavoriteCount = favoriteCounts.GetValueOrDefault(picture.Id, 0);
            }
        }
    }

    // 填充相册信息
    private async Task PopulateAlbumInfo(MyDbContext dbContext, List<PictureResponse> pictures, int userId)
    {
        if (!pictures.Any())
            return;

        // 获取当前用户拥有的图片ID列表
        var userPictureIds = pictures
            .Where(p => p.UserId == userId)
            .Select(p => p.Id)
            .ToList();

        if (!userPictureIds.Any())
            return;

        // 获取相册信息
        var pictureAlbums = await dbContext.Pictures
            .Where(p => userPictureIds.Contains(p.Id) && p.AlbumId.HasValue)
            .Select(p => new { p.Id, p.AlbumId, AlbumName = p.Album!.Name })
            .ToDictionaryAsync(p => p.Id, p => new { p.AlbumId, p.AlbumName });

        // 填充相册信息到图片响应中
        foreach (var picture in pictures)
        {
            if (picture.UserId == userId && pictureAlbums.TryGetValue(picture.Id, out var albumInfo))
            {
                picture.AlbumId = albumInfo.AlbumId;
                picture.AlbumName = albumInfo.AlbumName;
            }
        }
    }

    public async Task<(PictureResponse Picture, int Id)> UploadPictureAsync(
        string fileName,
        Stream fileStream,
        string contentType,
        int? userId,
        PermissionType permission = PermissionType.Public,
        int? albumId = null,
        int? storageModeId = null)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        if (!storageModeId.HasValue)
        {
            string configKey = userId == null
                ? "Storage:DefaultStorageModeId"
                : "Storage:DefaultStorageModeId";
            string? defaultMode = configuration[configKey];

            if (string.IsNullOrEmpty(defaultMode))
            {
                logger.LogError("未配置默认存储模式ID: {ConfigKey}", configKey);
                throw new InvalidOperationException($"未配置默认存储模式: {configKey}");
            }

            var defaultStorageMode = await dbContext.Set<StorageMode>()
                .FirstOrDefaultAsync(sm => sm.Id == int.Parse(defaultMode) && sm.IsEnabled);
            if (defaultStorageMode == null)
            {
                logger.LogError("根据名称 '{DefaultModeName}' 找不到已启用的默认存储模式。", defaultMode);
                throw new InvalidOperationException($"找不到默认存储模式 '{defaultMode}'。");
            }

            storageModeId = defaultStorageMode.Id;
        }
        else
        {
            var specifiedMode =
                await dbContext.Set<StorageMode>().FirstOrDefaultAsync(sm => sm.Id == storageModeId.Value);
            if (specifiedMode == null)
            {
                throw new ArgumentException($"找不到 ID 为 {storageModeId.Value} 的存储模式。");
            }

            if (!specifiedMode.IsEnabled)
            {
                throw new InvalidOperationException($"存储模式 '{specifiedMode.Name}' (ID: {storageModeId.Value}) 未启用。");
            }
        }

        ImageFormat convertToFormat = ImageFormat.WebP;

        // 高清图片压缩质量
        int quality = 100; // 默认值
        string hdQualityConfigKey = "Upload:HighQualityImageCompressionQuality";
        string? hdQualityConfig = configuration[hdQualityConfigKey];
        if (!string.IsNullOrEmpty(hdQualityConfig) && int.TryParse(hdQualityConfig, out int parsedHdQuality))
        {
            quality = Math.Clamp(parsedHdQuality, 50, 100); // 限制在 50-100 之间
        }
        else
        {
            logger.LogWarning("配置项 '{ConfigKey}' 未找到或无效，使用默认压缩质量: {DefaultQuality}", hdQualityConfigKey, quality);
        }

        string baseName = Guid.NewGuid().ToString();
        string originalFileExtension = Path.GetExtension(fileName);
        string originalStorageFileName = $"{baseName}{originalFileExtension}";

        string? tempOriginalLocalPath = null;
        string? tempConvertedHdLocalPath = null;
        string? tempThumbnailLocalPath = null;

        string? storedThumbnailPath = null;

        try
        {
            tempOriginalLocalPath = Path.GetTempFileName() + originalFileExtension;
            File.Move(Path.GetTempFileName(), tempOriginalLocalPath);
            await using (var tempFileStream = new FileStream(tempOriginalLocalPath, FileMode.Create))
            {
                await fileStream.CopyToAsync(tempFileStream);
            }

            string storedOriginalPath;
            await using (var originalLocalStream =
                         new FileStream(tempOriginalLocalPath, FileMode.Open, FileAccess.Read))
            {
                storedOriginalPath = await storageService.ExecuteAsync(storageModeId.Value,
                    provider => provider.SaveAsync(originalLocalStream, originalStorageFileName, contentType));
            }

            string sourceForHdProcessing = tempOriginalLocalPath;

            string convertedExtension = ImageHelper.GetFileExtensionFromFormat(convertToFormat);
            var hdStorageFileName = $"{baseName}-high-definition{convertedExtension}";
            var hdContentType = ImageHelper.GetMimeTypeFromFormat(convertToFormat);

            tempConvertedHdLocalPath = Path.GetTempFileName() + convertedExtension;
            File.Move(Path.GetTempFileName(), tempConvertedHdLocalPath);

            await ImageHelper.ConvertImageFormatAsync(sourceForHdProcessing, tempConvertedHdLocalPath, convertToFormat,
                quality);

            await using var convertedHdStream =
                new FileStream(tempConvertedHdLocalPath!, FileMode.Open, FileAccess.Read);
            var storedHdPath = await storageService.ExecuteAsync(storageModeId.Value,
                provider => provider.SaveAsync(convertedHdStream, hdStorageFileName!, hdContentType!));

            try
            {
                // 缩略图最大宽度
                int thumbnailMaxWidth = 500; // 默认值
                string thumbnailMaxWidthConfigKey = "Upload:ThumbnailMaxWidth";
                string? thumbnailMaxWidthConfig = configuration[thumbnailMaxWidthConfigKey];
                if (!string.IsNullOrEmpty(thumbnailMaxWidthConfig) && int.TryParse(thumbnailMaxWidthConfig, out int parsedMaxWidth))
                {
                    thumbnailMaxWidth = Math.Max(100, parsedMaxWidth); // 最小宽度 100
                }
                else
                {
                    logger.LogWarning("配置项 '{ConfigKey}' 未找到或无效，使用默认缩略图最大宽度: {DefaultMaxWidth}", thumbnailMaxWidthConfigKey, thumbnailMaxWidth);
                }

                // 缩略图压缩质量
                int thumbnailQuality = 75; // 默认值
                string thumbnailQualityConfigKey = "Upload:ThumbnailCompressionQuality";
                string? thumbnailQualityConfig = configuration[thumbnailQualityConfigKey];
                if (!string.IsNullOrEmpty(thumbnailQualityConfig) && int.TryParse(thumbnailQualityConfig, out int parsedThumbQuality))
                {
                    thumbnailQuality = Math.Clamp(parsedThumbQuality, 30, 90); // 限制在 30-90 之间
                }
                else
                {
                    logger.LogWarning("配置项 '{ConfigKey}' 未找到或无效，使用默认缩略图压缩质量: {DefaultThumbQuality}", thumbnailQualityConfigKey, thumbnailQuality);
                }

                tempThumbnailLocalPath = Path.GetTempFileName() + ".webp";
                File.Move(Path.GetTempFileName(), tempThumbnailLocalPath);
                await ImageHelper.CreateThumbnailAsync(tempOriginalLocalPath, tempThumbnailLocalPath, thumbnailMaxWidth, thumbnailQuality);

                string thumbnailUploadFileName = $"{baseName}-thumbnail.webp";
                await using var thumbnailFileStream =
                    new FileStream(tempThumbnailLocalPath!, FileMode.Open, FileAccess.Read);
                storedThumbnailPath = await storageService.ExecuteAsync(storageModeId.Value,
                    provider => provider.SaveAsync(thumbnailFileStream, thumbnailUploadFileName!, "image/webp"));
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "生成和上传缩略图失败 during initial upload");
            }

            string initialTitle = Path.GetFileNameWithoutExtension(fileName);
            string initialDescription = $"Uploaded on {DateTime.UtcNow}";

            await using var dbContextAsync = await contextFactory.CreateDbContextAsync();
            User? user = null;
            if (userId is not null)
            {
                user = await dbContext.Users.FirstOrDefaultAsync(u => u.Id == userId);
                if (user == null) throw new Exception("找不到指定的用户");
            }

            if (albumId.HasValue)
            {
                var album = await dbContext.Albums.Include(a => a.User)
                    .FirstOrDefaultAsync(a => a.Id == albumId.Value);

                if (album == null)
                {
                    throw new KeyNotFoundException($"找不到ID为{albumId.Value}的相册");
                }

                if (album.User.Id != userId)
                {
                    throw new Exception("您无权将图片添加到此相册");
                }
            }

            // 创建图片对象并保存到数据库
            var picture = new Picture
            {
                Name = initialTitle,
                Description = initialDescription,
                OriginalPath = storedOriginalPath,
                Path = storedHdPath,
                ThumbnailPath = storedThumbnailPath,
                User = user,
                Permission = permission,
                AlbumId = albumId,
                StorageModeId = storageModeId.Value,
            };

            dbContext.Pictures.Add(picture);
            await dbContext.SaveChangesAsync();

            if (userId != null)
            {
                await backgroundTaskQueue.QueuePictureProcessingTaskAsync(picture.Id, picture.OriginalPath);
                var visualRecognitionPayload = new Background.Processors.VisualRecognitionPayload
                {
                    PictureId = picture.Id,
                    UserIdForPicture = picture.UserId
                };
                await backgroundTaskQueue.QueueVisualRecognitionTaskAsync(visualRecognitionPayload);

                // 添加人脸识别任务
                var faceRecognitionPayload = new Background.Processors.FaceRecognitionPayload
                {
                    PictureId = picture.Id,
                    UserIdForPicture = picture.UserId
                };
                await backgroundTaskQueue.QueueFaceRecognitionTaskAsync(faceRecognitionPayload);
            }

            var pictureResponse = mappingService.MapPictureToResponse(picture);
            return (pictureResponse, picture.Id);
        }
        finally
        {
            if (!string.IsNullOrEmpty(tempOriginalLocalPath) && File.Exists(tempOriginalLocalPath))
            {
                try
                {
                    File.Delete(tempOriginalLocalPath);
                    Console.WriteLine(tempOriginalLocalPath);
                }
                catch
                {
                    /* ignored */
                }
            }

            if (!string.IsNullOrEmpty(tempConvertedHdLocalPath) && File.Exists(tempConvertedHdLocalPath))
            {
                try
                {
                    File.Delete(tempConvertedHdLocalPath);
                    Console.WriteLine(tempConvertedHdLocalPath);
                }
                catch
                {
                    /* ignored */
                }
            }

            if (!string.IsNullOrEmpty(tempThumbnailLocalPath) && File.Exists(tempThumbnailLocalPath))
            {
                try
                {
                    File.Delete(tempThumbnailLocalPath);
                    Console.WriteLine(tempThumbnailLocalPath);


                }
                catch
                {
                    /* ignored */
                }
            }
        }
    }

    public async Task<ExifInfo> GetPictureExifInfoAsync(int pictureId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        var picture = await dbContext.Pictures.FindAsync(pictureId);

        if (picture == null)
            throw new KeyNotFoundException($"找不到ID为{pictureId}的图片");

        // 如果已有保存的EXIF信息，则直接返回
        if (!string.IsNullOrEmpty(picture.ExifInfoJson))
        {
            var exifInfo = JsonSerializer.Deserialize<ExifInfo>(picture.ExifInfoJson);
            return exifInfo ?? new ExifInfo { ErrorMessage = "无法解析EXIF信息" };
        }

        // 否则从文件中提取
        string fullPath = Path.Combine(Directory.GetCurrentDirectory(), picture.Path.TrimStart('/'));
        if (!File.Exists(fullPath))
        {
            return new ExifInfo { ErrorMessage = "找不到图片文件" };
        }

        return await ImageHelper.ExtractExifInfoAsync(fullPath);
    }

    public async Task<Dictionary<int, (bool Success, string? ErrorMessage, int? UserId)>> DeleteMultiplePicturesAsync(
        List<int> pictureIds)
    {
        var results = new Dictionary<int, (bool Success, string? ErrorMessage, int? UserId)>();
        if (pictureIds.Count == 0)
            return results;

        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 在查询时包含 StorageModeId
        var picturesToDelete = await dbContext.Pictures
            .Include(p => p.User)
            .Where(p => pictureIds.Contains(p.Id))
            .Select(p => new
            {
                p.Id,
                p.Path,
                p.ThumbnailPath,
                p.OriginalPath,
                UserId = p.User != null ? (int?)p.User.Id : null,
                p.StorageModeId // 获取 StorageModeId
            })
            .ToListAsync();

        var foundPictureIds = picturesToDelete.Select(p => p.Id).ToHashSet();
        foreach (var id in pictureIds.Where(id => !foundPictureIds.Contains(id)))
        {
            results[id] = (false, "找不到此图片", null);
        }

        // 从数据库中删除记录
        if (picturesToDelete.Any())
        {
            var idsToRemove = picturesToDelete.Select(p => p.Id).ToList();
            // EF Core 7+ 可以使用 ExecuteDeleteAsync
            await dbContext.Pictures.Where(p => idsToRemove.Contains(p.Id)).ExecuteDeleteAsync();
            // 对于旧版本 EF Core:
            // var entitiesToRemove = await dbContext.Pictures.Where(p => idsToRemove.Contains(p.Id)).ToListAsync();
            // dbContext.Pictures.RemoveRange(entitiesToRemove);
            // await dbContext.SaveChangesAsync();
        }

        // 从存储中删除文件
        foreach (var picInfo in picturesToDelete)
        {
            try
            {
                string? errorMsg = null;
                if (picInfo.StorageModeId < 0)
                {
                    results[picInfo.Id] = (false, "图片记录缺少有效的StorageModeId，无法删除文件。", picInfo.UserId);
                    logger.LogWarning("图片 {PictureId} 缺少 StorageModeId，跳过文件删除。", picInfo.Id);
                    continue;
                }

                try
                {
                    if (!string.IsNullOrEmpty(picInfo.OriginalPath))
                    {
                        await storageService.ExecuteAsync(picInfo.StorageModeId,
                            provider => provider.DeleteAsync(picInfo.OriginalPath));
                    }

                    if (!string.IsNullOrEmpty(picInfo.Path) && picInfo.Path != picInfo.OriginalPath)
                    {
                        await storageService.ExecuteAsync(picInfo.StorageModeId,
                            provider => provider.DeleteAsync(picInfo.Path));
                    }

                    if (!string.IsNullOrEmpty(picInfo.ThumbnailPath))
                    {
                        await storageService.ExecuteAsync(picInfo.StorageModeId,
                            provider => provider.DeleteAsync(picInfo.ThumbnailPath));
                    }
                }
                catch (Exception ex)
                {
                    errorMsg = $"数据库记录已删除，但删除文件失败: {ex.Message}";
                    logger.LogError(ex, "删除图片文件时出错 (ID: {PictureId})", picInfo.Id);
                }

                results[picInfo.Id] = (true, errorMsg, picInfo.UserId);
            }
            catch (Exception ex)
            {
                results[picInfo.Id] = (false, $"处理图片删除时出错: {ex.Message}", picInfo.UserId);
                logger.LogError(ex, "处理图片删除的外部循环出错 (ID: {PictureId})", picInfo.Id);
            }
        }

        return results;
    }

    public async Task<(PictureResponse Picture, int? UserId)> UpdatePictureAsync(
        int pictureId,
        string? name = null,
        string? description = null,
        List<string>? tags = null,
        PermissionType? permission = null)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var picture = await dbContext.Pictures
            .Include(p => p.User)
            .Include(p => p.Tags)
            .Include(p => p.StorageMode)
            .FirstOrDefaultAsync(p => p.Id == pictureId);

        if (picture == null)
            throw new KeyNotFoundException($"找不到ID为{pictureId}的图片");

        var userId = picture.User?.Id;

        if (!string.IsNullOrWhiteSpace(name))
        {
            picture.Name = name.Trim();
        }

        if (!string.IsNullOrWhiteSpace(description))
        {
            picture.Description = description.Trim();
        }

        if (permission.HasValue)
        {
            picture.Permission = permission.Value;
        }

        // 只有当名称或描述发生变化时才更新嵌入向量
        if (!string.IsNullOrWhiteSpace(name) || !string.IsNullOrWhiteSpace(description))
        {
            try
            {
                var combinedText = $"{picture.Name}. {picture.Description}";
                var embedding = await embeddingService.GetEmbeddingAsync(combinedText);

                // 只有在成功获取到非空嵌入向量时才更新
                if (embedding != null && embedding.Length > 0)
                {
                    picture.Embedding = embedding;
                }
                else
                {
                    // 记录获取到空向量的警告
                    logger.LogWarning("图片 {PictureId} 的嵌入向量为空，跳过向量更新", pictureId);
                }
            }
            catch (Exception ex)
            {
                // 记录错误但不抛出异常，允许其他字段的更新继续进行
                logger.LogError(ex, "更新图片 {PictureId} 的嵌入向量时出错", pictureId);
                // 不设置 picture.Embedding，保持原值不变
            }
        }

        if (tags != null)
        {
            picture.Tags?.Clear();

            foreach (var tagName in tags.Where(t => !string.IsNullOrWhiteSpace(t)))
            {
                var tag = await dbContext.Tags.FirstOrDefaultAsync(t => t.Name.ToLower() == tagName.ToLower().Trim());

                if (tag == null)
                {
                    tag = new Tag { Name = tagName.Trim() };
                    dbContext.Tags.Add(tag);
                }

                picture.Tags?.Add(tag);
            }
        }

        picture.UpdatedAt = DateTime.UtcNow;

        await dbContext.SaveChangesAsync();
        var pictureResponse = mappingService.MapPictureToResponse(picture);
        return (pictureResponse, userId);
    }

    public async Task<bool> FavoritePictureAsync(int pictureId, int userId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 检查图片是否存在
        var picture = await dbContext.Pictures.FindAsync(pictureId);
        if (picture == null)
            throw new KeyNotFoundException($"找不到ID为{pictureId}的图片");

        // 检查用户是否存在
        var user = await dbContext.Users.FindAsync(userId);
        if (user == null)
            throw new KeyNotFoundException($"找不到ID为{userId}的用户");

        // 检查是否已经收藏
        var existingFavorite = await dbContext.Favorites
            .FirstOrDefaultAsync(f => f.PictureId == pictureId && f.User.Id == userId);

        if (existingFavorite != null)
            throw new InvalidOperationException("您已经收藏过此图片");

        // 创建新收藏
        var favorite = new Favorite
        {
            PictureId = pictureId,
            User = user,
            CreatedAt = DateTime.UtcNow
        };

        dbContext.Favorites.Add(favorite);
        await dbContext.SaveChangesAsync();

        return true;
    }

    public async Task<bool> UnfavoritePictureAsync(int pictureId, int userId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 查找收藏记录
        var favorite = await dbContext.Favorites
            .FirstOrDefaultAsync(f => f.PictureId == pictureId && f.User.Id == userId);

        if (favorite == null)
            throw new KeyNotFoundException($"未找到该图片的收藏记录");

        // 移除收藏
        dbContext.Favorites.Remove(favorite);
        await dbContext.SaveChangesAsync();

        return true;
    }

    public async Task<bool> IsPictureFavoritedByUserAsync(int pictureId, int userId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        return await dbContext.Favorites
            .AnyAsync(f => f.PictureId == pictureId && f.User.Id == userId);
    }

    public async Task<Picture?> GetPictureByIdAsync(int pictureId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        var picture = await dbContext.Pictures
            .Include(p => p.User)
            .Include(p => p.Tags)
            .Include(p => p.StorageMode) // 确保加载 StorageMode 以便 MapPictureToResponseAsync 正确工作
            .AsNoTracking() // 如果只是读取数据，使用 AsNoTracking 可以提高性能
            .FirstOrDefaultAsync(p => p.Id == pictureId);

        if (picture == null)
        {
            logger.LogWarning("GetPictureByIdAsync: Picture with ID {PictureId} not found.", pictureId);
            return null;
        }

        var pictureResponse = mappingService.MapPictureToResponse(picture);

        return picture;
    }
}