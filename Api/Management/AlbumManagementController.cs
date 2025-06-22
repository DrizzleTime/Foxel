using Foxel.Models;
using Foxel.Models.Request.Album;
using Foxel.Models.Response.Album;
using Foxel.Models.Response.Picture;
using Foxel.Services.Management;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api.Management
{
    [Authorize(Roles = "Administrator")]
    [Route("api/management/album")]
    public class AlbumManagementController(IAlbumManagementService albumManagementService) : BaseApiController
    {
        [HttpGet("get_albums")]
        public async Task<ActionResult<PaginatedResult<AlbumResponse>>> GetAlbums(
            [FromQuery] int page = 1,
            [FromQuery] int pageSize = 10,
            [FromQuery] string? searchQuery = null,
            [FromQuery] int? userId = null)
        {
            try
            {
                var result = await albumManagementService.GetAlbumsAsync(page, pageSize, searchQuery, userId);
                return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
            }
            catch (Exception ex)
            {
                return PaginatedError<AlbumResponse>($"获取相册列表失败: {ex.Message}", 500);
            }
        }

        [HttpGet("get_album/{id}")]
        public async Task<ActionResult<BaseResult<AlbumResponse>>> GetAlbumById(int id)
        {
            try
            {
                var album = await albumManagementService.GetAlbumByIdAsync(id);
                return Success(album, "相册获取成功");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<AlbumResponse>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return Error<AlbumResponse>($"获取相册失败: {ex.Message}", 500);
            }
        }

        [HttpPost("create_album")]
        public async Task<ActionResult<BaseResult<AlbumResponse>>> CreateAlbum([FromBody] AlbumCreateRequest request)
        {
            try
            {
                var userId = GetCurrentUserId();
                if (userId is null) return Error<AlbumResponse>("用户未登录或无法识别用户", 401);
                var album = await albumManagementService.CreateAlbumAsync(request, (int)userId);
                return Success(album, "相册创建成功");
            }
            catch (Exception ex)
            {
                return Error<AlbumResponse>($"创建相册失败: {ex.Message}", 500);
            }
        }

        [HttpPost("update_album/{id}")]
        public async Task<ActionResult<BaseResult<AlbumResponse>>> UpdateAlbum(int id,
            [FromBody] AlbumUpdateRequest request)
        {
            try
            {
                var album = await albumManagementService.UpdateAlbumAsync(id, request);
                return Success(album, "相册更新成功");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<AlbumResponse>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return Error<AlbumResponse>($"更新相册失败: {ex.Message}", 500);
            }
        }

        [HttpPost("delete_album")]
        public async Task<ActionResult<BaseResult<bool>>> DeleteAlbum([FromBody] int id) // Or [FromQuery] int id
        {
            try
            {
                var result = await albumManagementService.DeleteAlbumAsync(id);
                return Success(result, "相册删除成功");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<bool>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return Error<bool>($"删除相册失败: {ex.Message}", 500);
            }
        }

        [HttpPost("batch_delete_albums")]
        public async Task<ActionResult<BaseResult<BatchDeleteResult>>> BatchDeleteAlbums([FromBody] List<int> ids)
        {
            try
            {
                if (ids == null || ids.Count == 0)
                {
                    return Error<BatchDeleteResult>("未提供相册ID");
                }

                var result = await albumManagementService.BatchDeleteAlbumsAsync(ids);
                return Success(result, $"成功删除 {result.SuccessCount} 个相册，失败 {result.FailedCount} 个");
            }
            catch (Exception ex)
            {
                return Error<BatchDeleteResult>($"批量删除相册失败: {ex.Message}", 500);
            }
        }

        [HttpGet("get_albums_by_user/{userId}")]
        public async Task<ActionResult<PaginatedResult<AlbumResponse>>> GetAlbumsByUserId(
            int userId, [FromQuery] int page = 1, [FromQuery] int pageSize = 10)
        {
            try
            {
                var result = await albumManagementService.GetAlbumsByUserIdAsync(userId, page, pageSize);
                return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
            }
            catch (Exception ex)
            {
                return PaginatedError<AlbumResponse>($"获取用户相册列表失败: {ex.Message}", 500);
            }
        }

        [HttpPost("{albumId}/picture/{pictureId}/add")]
        public async Task<ActionResult<BaseResult<bool>>> AddPictureToAlbum(int albumId, int pictureId)
        {
            try
            {
                var result = await albumManagementService.AddPictureToAlbumAsync(albumId, pictureId);
                return Success(result, "图片已成功添加到相册");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<bool>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return Error<bool>($"添加图片到相册失败: {ex.Message}", 500);
            }
        }

        [HttpPost("{albumId}/picture/{pictureId}/remove")]
        public async Task<ActionResult<BaseResult<bool>>> RemovePictureFromAlbum(int albumId, int pictureId)
        {
            try
            {
                var result = await albumManagementService.RemovePictureFromAlbumAsync(albumId, pictureId);
                return Success(result, "图片已成功从相册移除");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<bool>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return Error<bool>($"从相册移除图片失败: {ex.Message}", 500);
            }
        }

        [HttpGet("{albumId}/pictures")]
        public async Task<ActionResult<PaginatedResult<PictureResponse>>> GetPicturesInAlbum(
            int albumId, [FromQuery] int page = 1, [FromQuery] int pageSize = 10)
        {
            try
            {
                var result = await albumManagementService.GetPicturesInAlbumAsync(albumId, page, pageSize);
                return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
            }
            catch (KeyNotFoundException knfex)
            {
                return PaginatedError<PictureResponse>(knfex.Message, 404);
            }
            catch (Exception ex)
            {
                return PaginatedError<PictureResponse>($"获取相册内图片失败: {ex.Message}", 500);
            }
        }

        [HttpPost("{albumId}/set_cover/{pictureId}")]
        public async Task<ActionResult<BaseResult<bool>>> SetAlbumCover(int albumId, int pictureId)
        {
            try
            {
                var result = await albumManagementService.SetAlbumCoverAsync(albumId, pictureId);
                return Success(result, "相册封面设置成功");
            }
            catch (KeyNotFoundException knfex)
            {
                return Error<bool>(knfex.Message, 404);
            }
            catch (InvalidOperationException ioex)
            {
                return Error<bool>(ioex.Message, 400);
            }
            catch (Exception ex)
            {
                return Error<bool>($"设置相册封面失败: {ex.Message}", 500);
            }
        }
    }
}