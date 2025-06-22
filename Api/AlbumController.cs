using Foxel.Models;
using Foxel.Models.Request.Album;
using Foxel.Models.Response.Album;
using Foxel.Services.Media;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api;

[Authorize]
[Route("api/album")]
public class AlbumController(IAlbumService albumService) : BaseApiController
{
    [HttpGet("get_albums")]
    public async Task<ActionResult<PaginatedResult<AlbumResponse>>> GetAlbums(
        [FromQuery] int page = 1, [FromQuery] int pageSize = 10)
    {
        var userId = GetCurrentUserId();
        try
        {
            var albums = await albumService.GetAlbumsAsync(page, pageSize, userId);
            return PaginatedSuccess(albums.Data, albums.TotalCount, albums.Page, albums.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<AlbumResponse>($"获取相册失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_album/{id}")]
    public async Task<ActionResult<BaseResult<AlbumResponse>>> GetAlbumById(int id)
    {
        try
        {
            var album = await albumService.GetAlbumByIdAsync(id);
            return Success(album, "相册获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<AlbumResponse>("找不到指定相册", 404);
        }
        catch (Exception ex)
        {
            return Error<AlbumResponse>($"获取相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("create_album")]
    [Authorize]
    public async Task<ActionResult<BaseResult<AlbumResponse>>> CreateAlbum([FromBody] CreateAlbumRequest request)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (userId == null)
                return Error<AlbumResponse>("无法识别用户信息", 401);

            var album = await albumService.CreateAlbumAsync(request.Name, request.Description, userId.Value, request.CoverPictureId);
            return Success(album, "相册创建成功");
        }
        catch (Exception ex)
        {
            return Error<AlbumResponse>($"创建相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("update_album")]
    [Authorize]
    public async Task<ActionResult<BaseResult<AlbumResponse>>> UpdateAlbum([FromBody] UpdateAlbumRequest request)
    {
        try
        {
            var currentUserId = GetCurrentUserId();
            if (currentUserId == null)
                return Error<AlbumResponse>("无法识别用户信息", 401);

            var album = await albumService.UpdateAlbumAsync(request.Id, request.Name, request.Description, currentUserId, request.CoverPictureId);
            return Success(album, "相册更新成功");
        }
        catch (UnauthorizedAccessException)
        {
            return Error<AlbumResponse>("您没有权限更新此相册", 403);
        }
        catch (KeyNotFoundException)
        {
            return Error<AlbumResponse>("找不到要更新的相册", 404);
        }
        catch (Exception ex)
        {
            return Error<AlbumResponse>($"更新相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_album")]
    [Authorize]
    public async Task<ActionResult<BaseResult<bool>>> DeleteAlbum([FromBody] int id)
    {
        try
        {
            var currentUserId = GetCurrentUserId();
            if (currentUserId == null)
                return Error<bool>("无法识别用户信息", 401);

            var result = await albumService.DeleteAlbumAsync(id);
            return Success(result, "相册删除成功");
        }
        catch (UnauthorizedAccessException)
        {
            return Error<bool>("您没有权限删除此相册", 403);
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到要删除的相册", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"删除相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("add_pictures")]
    [Authorize]
    public async Task<ActionResult<BaseResult<bool>>> AddPicturesToAlbum([FromBody] AlbumPicturesRequest request)
    {
        try
        {
            if (request.PictureIds.Count == 0)
            {
                return Error<bool>("未提供图片ID");
            }

            var result = await albumService.AddPicturesToAlbumAsync(request.AlbumId, request.PictureIds);
            return Success(result, $"已将 {request.PictureIds.Count} 张图片添加到相册");
        }
        catch (UnauthorizedAccessException)
        {
            return Error<bool>("您没有权限修改此相册", 403);
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>($"添加失败: {ex.Message}", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"添加图片到相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("add_picture")]
    [Authorize]
    public async Task<ActionResult<BaseResult<bool>>> AddPictureToAlbum([FromBody] AlbumPictureRequest request)
    {
        try
        {
            var result = await albumService.AddPictureToAlbumAsync(request.AlbumId, request.PictureId);
            return Success(result, "图片已添加到相册");
        }
        catch (UnauthorizedAccessException)
        {
            return Error<bool>("您没有权限修改此相册", 403);
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>($"添加失败: {ex.Message}", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"添加图片到相册失败: {ex.Message}", 500);
        }
    }

    [HttpPost("remove_picture")]
    [Authorize]
    public async Task<ActionResult<BaseResult<bool>>> RemovePictureFromAlbum([FromBody] AlbumPictureRequest request)
    {
        try
        {
            var result = await albumService.RemovePictureFromAlbumAsync(request.AlbumId, request.PictureId);
            return Success(result, "图片已从相册移除");
        }
        catch (UnauthorizedAccessException)
        {
            return Error<bool>("您没有权限修改此相册", 403);
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>($"移除失败: {ex.Message}", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"从相册移除图片失败: {ex.Message}", 500);
        }
    }

}