using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Foxel.Models;
using Foxel.Models.Response.Picture;
using Foxel.Services.Management;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/picture")]
public class PictureManagementController(IPictureManagementService pictureManagementService) : BaseApiController
{
    [HttpGet("get_pictures")]
    public async Task<ActionResult<PaginatedResult<PictureResponse>>> GetPictures(
        [FromQuery] int page = 1, 
        [FromQuery] int pageSize = 10,
        [FromQuery] string? searchQuery = null,
        [FromQuery] int? userId = null)
    {
        try
        {
            var pictures = await pictureManagementService.GetPicturesAsync(page, pageSize, searchQuery, userId);
            return PaginatedSuccess(pictures.Data, pictures.TotalCount, pictures.Page, pictures.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<PictureResponse>($"获取图片列表失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_picture/{id}")]
    public async Task<ActionResult<BaseResult<PictureResponse>>> GetPictureById(int id)
    {
        try
        {
            var picture = await pictureManagementService.GetPictureByIdAsync(id);
            return Success(picture, "图片获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<PictureResponse>("找不到指定图片", 404);
        }
        catch (Exception ex)
        {
            return Error<PictureResponse>($"获取图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_picture")]
    public async Task<ActionResult<BaseResult<bool>>> DeletePicture([FromBody] int id)
    {
        try
        {
            var result = await pictureManagementService.DeletePictureAsync(id);
            return Success(result, "图片删除成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到要删除的图片", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"删除图片失败: {ex.Message}", 500);
        }
    }

    [HttpPost("batch_delete_pictures")]
    public async Task<ActionResult<BaseResult<BatchDeleteResult>>> BatchDeletePictures([FromBody] List<int> ids)
    {
        try
        {
            if (ids.Count == 0)
            {
                return Error<BatchDeleteResult>("未提供图片ID");
            }

            var result = await pictureManagementService.BatchDeletePicturesAsync(ids);
            return Success(result, $"成功删除 {result.SuccessCount} 张图片，失败 {result.FailedCount} 张");
        }
        catch (Exception ex)
        {
            return Error<BatchDeleteResult>($"批量删除图片失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_pictures_by_user/{userId}")]
    public async Task<ActionResult<PaginatedResult<PictureResponse>>> GetPicturesByUserId(
        int userId, [FromQuery] int page = 1, [FromQuery] int pageSize = 10)
    {
        try
        {
            var pictures = await pictureManagementService.GetPicturesByUserIdAsync(userId, page, pageSize);
            return PaginatedSuccess(pictures.Data, pictures.TotalCount, pictures.Page, pictures.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<PictureResponse>($"获取用户图片列表失败: {ex.Message}", 500);
        }
    }
}
