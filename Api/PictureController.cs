using Foxel.Models;
using Foxel.Models.DataBase;
using Foxel.Models.Request.Picture;
using Foxel.Models.Response.Picture;
using Foxel.Services.Media;
using Foxel.Services.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Foxel.Services.Configuration;

namespace Foxel.Api;

[Authorize]
[Route("api/picture")]
public class PictureController(IPictureService pictureService, IStorageService storageService, ILogger<PictureController> logger, IConfigService configuration) : BaseApiController
{
    [HttpGet("get_pictures")]
    public async Task<ActionResult<PaginatedResult<PictureResponse>>> GetPictures(
        [FromQuery] FilteredPicturesRequest request)
    {
        try
        {
            List<string>? tagsList = null;
            if (!string.IsNullOrWhiteSpace(request.Tags))
            {
                tagsList = request.Tags.Split(',')
                    .Select(t => t.Trim())
                    .Where(t => !string.IsNullOrWhiteSpace(t))
                    .ToList();
            }

            var currentUserId = GetCurrentUserId();

            var result = await pictureService.GetPicturesAsync(
                request.Page,
                request.PageSize,
                request.SearchQuery,
                tagsList,
                request.StartDate,
                request.EndDate,
                currentUserId,
                request.SortBy,
                request.OnlyWithGps,
                request.UseVectorSearch,
                request.SimilarityThreshold,
                request.ExcludeAlbumId,
                request.AlbumId,
                request.OnlyFavorites,
                request.OwnerId,
                request.IncludeAllPublic
            );

            return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<PictureResponse>($"获取图片失败: {ex.Message}", 500);
        }
    }

    [AllowAnonymous]
    [HttpPost("upload_picture")]
    [Consumes("multipart/form-data")]
    public async Task<ActionResult<BaseResult<PictureResponse>>> UploadPicture(
        [FromForm] UploadPictureRequest request) // UploadPictureRequest 模型需要添加 StorageModeId 属性
    {
        if (request.File.Length == 0)
            return Error<PictureResponse>("没有上传文件");

        try
        {
            var userId = GetCurrentUserId();

            if (userId == null)
            {
                var enableAnonymousUpload = configuration["AppSettings:EnableAnonymousImageHosting"];
                if (string.Equals(enableAnonymousUpload, "false", StringComparison.OrdinalIgnoreCase))
                {
                    return Error<PictureResponse>("匿名上传功能已关闭，请登录后操作", 403);
                }
            }

            await using var stream = request.File.OpenReadStream();
            var result = await pictureService.UploadPictureAsync(
                request.File.FileName,
                stream,
                request.File.ContentType,
                userId,
                (PermissionType)request.Permission!, // 确保 PermissionType 的转换是安全的
                request.AlbumId,
                request.StorageModeId // 传递 StorageModeId
            );

            var picture = result.Picture;

            return Success(picture, "图片上传成功");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<PictureResponse>(ex.Message, 404);
        }
        catch (Exception ex)
        {
            return Error<PictureResponse>($"上传图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_pictures")]
    public async Task<ActionResult<BaseResult<object>>> DeleteMultiplePictures(
        [FromBody] DeleteMultiplePicturesRequest request)
    {
        try
        {
            var currentUserId = GetCurrentUserId();
            if (currentUserId == null)
                return Error<object>("无法识别用户信息");

            if (!request.PictureIds.Any())
                return Error<object>("未提供要删除的图片ID");

            // 获取删除结果
            var results = await pictureService.DeleteMultiplePicturesAsync(request.PictureIds);

            // 权限验证和处理结果
            var unauthorizedIds = new List<int>();
            var notFoundIds = new List<int>();
            var successIds = new List<int>();
            var errors = new Dictionary<int, string>();

            foreach (var (pictureId, (success, errorMessage, ownerId)) in results)
            {
                // 检查权限
                if (ownerId.HasValue && ownerId.Value != currentUserId.Value)
                {
                    unauthorizedIds.Add(pictureId);
                    continue;
                }

                if (!success)
                {
                    notFoundIds.Add(pictureId);
                }
                else if (!string.IsNullOrEmpty(errorMessage))
                {
                    errors[pictureId] = errorMessage;
                }
                else
                {
                    successIds.Add(pictureId);
                }
            }

            // 如果有未授权或其他错误，返回适当的响应
            if (unauthorizedIds.Any() || notFoundIds.Any() || errors.Any())
            {
                var messages = new List<string>();

                if (unauthorizedIds.Any())
                    messages.Add($"无权删除以下图片: {string.Join(", ", unauthorizedIds)}");

                if (notFoundIds.Any())
                    messages.Add($"找不到以下图片: {string.Join(", ", notFoundIds)}");

                if (errors.Any())
                    messages.Add(string.Join("; ", errors.Select(e => $"图片ID {e.Key}: {e.Value}")));

                return StatusCode(207, new BaseResult<object>
                {
                    Success = successIds.Any(),
                    Message = string.Join("; ", messages),
                    StatusCode = 207,
                    Data = new
                    {
                        SuccessCount = successIds.Count,
                        SuccessIds = successIds,
                        UnauthorizedIds = unauthorizedIds,
                        NotFoundIds = notFoundIds,
                        Errors = errors
                    }
                });
            }

            return Success<object>($"成功删除 {successIds.Count} 张图片");
        }
        catch (Exception ex)
        {
            return Error<object>($"删除图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("update_picture")]
    public async Task<ActionResult<BaseResult<PictureResponse>>> UpdatePicture(
        [FromBody] UpdatePictureRequestWithId request)
    {
        try
        {
            var currentUserId = GetCurrentUserId();
            if (currentUserId == null)
                return Error<PictureResponse>("无法识别用户信息");

            (PictureResponse picture, int? ownerId) = await pictureService.UpdatePictureAsync(
                request.Id, request.Name, request.Description, request.Tags, (PermissionType?)request.Permission);

            // 权限验证
            if (ownerId.HasValue && ownerId.Value != currentUserId.Value)
            {
                return Error<PictureResponse>("您没有权限更新此图片", 403);
            }

            return Success(picture, "图片信息已成功更新");
        }
        catch (KeyNotFoundException)
        {
            return Error<PictureResponse>("找不到要更新的图片", 404);
        }
        catch (Exception ex)
        {
            return Error<PictureResponse>($"更新图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("favorite")]
    public async Task<ActionResult<BaseResult<bool>>> FavoritePicture([FromBody] FavoriteRequest request)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (userId == null)
                return Error<bool>("无法识别用户信息", 401);

            var result = await pictureService.FavoritePictureAsync(request.PictureId, userId.Value);
            return Success(result, "图片收藏成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到指定图片", 404);
        }
        catch (InvalidOperationException ex)
        {
            return Error<bool>(ex.Message);
        }
        catch (Exception ex)
        {
            return Error<bool>($"收藏图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("unfavorite")]
    public async Task<ActionResult<BaseResult<bool>>> UnfavoritePicture([FromBody] FavoriteRequest request)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (userId == null)
                return Error<bool>("无法识别用户信息", 401);

            var result = await pictureService.UnfavoritePictureAsync(request.PictureId, userId.Value);
            return Success(result, "已取消收藏");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到指定图片或收藏记录", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"取消收藏失败: {ex.Message}", 500);
        }
    }

    [HttpGet("file/{pictureId}")]
    [AllowAnonymous]
    public async Task<IActionResult> GetPictureFile(int pictureId)
    {
        try
        {
            var picture = await pictureService.GetPictureByIdAsync(pictureId);
            if (picture == null)
            {
                logger.LogWarning("GetPictureFile: Picture with ID {PictureId} not found.", pictureId);
                return NotFound("Picture not found.");
            }
            var currentUserId = GetUserIdFromCookie();
            if (picture.Permission != PermissionType.Public)
            {
                if (currentUserId == null || picture.UserId != currentUserId.Value)
                {
                    logger.LogWarning("GetPictureFile: User {UserId} forbidden to access picture {PictureId}.", currentUserId, pictureId);
                    return Forbid();
                }
            }

            // 3. 使用 StorageService 下载文件
            string tempFilePath = await storageService.ExecuteAsync(
                picture.StorageModeId,
                provider => provider.DownloadFileAsync(picture.Path)
            );

            if (string.IsNullOrEmpty(tempFilePath) || !System.IO.File.Exists(tempFilePath))
            {
                logger.LogError("GetPictureFile: Failed to download file or file not found at temp path for picture ID {PictureId}. TempPath: {TempPath}", pictureId, tempFilePath);
                return StatusCode(500, "Failed to retrieve file from storage.");
            }
            // 4. 确定内容类型
            string contentType = GetContentTypeFromPath(tempFilePath);

            // 5. 返回文件
            return PhysicalFile(tempFilePath, contentType, Path.GetFileName(picture.Name));
        }
        catch (KeyNotFoundException knfEx)
        {
            logger.LogWarning(knfEx, "GetPictureFile: Resource not found for picture ID {PictureId}.", pictureId);
            return NotFound($"Resource related to picture ID {pictureId} not found.");
        }
        catch (FileNotFoundException fnfEx)
        {
            logger.LogWarning(fnfEx, "GetPictureFile: File not found in storage for picture ID {PictureId}.", pictureId);
            return NotFound("File not found in storage.");
        }
        catch (NotImplementedException niEx)
        {
            logger.LogError(niEx, "GetPictureFile: DownloadFileAsync not implemented for the storage provider of picture ID {PictureId}.", pictureId);
            return StatusCode(501, "File download is not supported for this storage type.");
        }
        catch (InvalidOperationException ioEx)
        {
            logger.LogError(ioEx, "GetPictureFile: Invalid operation for picture ID {PictureId}.", pictureId);
            return StatusCode(500, $"Error processing file request: {ioEx.Message}");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "GetPictureFile: Error getting file for picture ID {PictureId}", pictureId);
            return StatusCode(500, "An error occurred while retrieving the file.");
        }
    }

    private string GetContentTypeFromPath(string path)
    {
        string extension = Path.GetExtension(path).ToLowerInvariant();

        return extension switch
        {
            ".jpg" or ".jpeg" => "image/jpeg",
            ".png" => "image/png",
            ".gif" => "image/gif",
            ".bmp" => "image/bmp",
            ".webp" => "image/webp",
            ".svg" => "image/svg+xml",
            ".mp4" => "video/mp4",
            ".avi" => "video/x-msvideo",
            ".mov" => "video/quicktime",
            ".pdf" => "application/pdf",
            ".doc" or ".docx" => "application/msword",
            ".xls" or ".xlsx" => "application/vnd.ms-excel",
            _ => "application/octet-stream"
        };
    }
}