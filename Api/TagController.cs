using Foxel.Models;
using Foxel.Models.Request.Tag;
using Foxel.Models.Response.Tag;
using Foxel.Services.Media;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api;

[Route("api/tag")]
public class TagController(ITagService tagService) : BaseApiController
{
    [HttpGet("get_tags")]
    public async Task<ActionResult<PaginatedResult<TagResponse>>> GetFilteredTags([FromQuery] FilteredTagsRequest request)
    {
        try
        {
            var result = await tagService.GetFilteredTagsAsync(
                request.Page,
                request.PageSize,
                request.SearchQuery,
                request.SortBy,
                request.SortDirection
            );
            
            return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<TagResponse>($"获取标签失败: {ex.Message}", 500);
        }
    }

    // 添加一个简化的获取所有标签的方法，内部使用GetFilteredTagsAsync
    [HttpGet("all")]
    public async Task<ActionResult<BaseResult<List<TagResponse>>>> GetAllTags()
    {
        try
        {
            // 使用过滤方法但获取更多数据
            var result = await tagService.GetFilteredTagsAsync(
                page: 1,
                pageSize: 1000, // 设置一个较大值获取所有标签
                sortBy: "pictureCount",
                sortDirection: "desc"
            );
            
            return Success(result.Data, "标签获取成功");
        }
        catch (Exception ex)
        {
            return Error<List<TagResponse>>($"获取标签失败: {ex.Message}", 500);
        }
    }

    [HttpGet("{id}")]
    public async Task<ActionResult<BaseResult<TagResponse>>> GetTagById(int id)
    {
        try
        {
            var tag = await tagService.GetTagByIdAsync(id);
            return Success(tag, "标签获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<TagResponse>("找不到指定标签", 404);
        }
        catch (Exception ex)
        {
            return Error<TagResponse>($"获取标签失败: {ex.Message}", 500);
        }
    }
    
    [HttpPost("create_tag")]
    [Authorize]
    public async Task<ActionResult<BaseResult<TagResponse>>> CreateTag([FromBody] CreateTagRequest request)
    {
        try
        {
            var tag = await tagService.CreateTagAsync(request.Name, request.Description);
            return Success(tag, "标签创建成功");
        }
        catch (Exception ex)
        {
            return Error<TagResponse>($"创建标签失败: {ex.Message}", 500);
        }
    }
    
    [HttpPost("update_tag")]
    [Authorize]
    public async Task<ActionResult<BaseResult<TagResponse>>> UpdateTag([FromBody] UpdateTagRequest request)
    {
        try
        {
            var tag = await tagService.UpdateTagAsync(request.Id, request.Name, request.Description);
            return Success(tag, "标签更新成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<TagResponse>("找不到要更新的标签", 404);
        }
        catch (Exception ex)
        {
            return Error<TagResponse>($"更新标签失败: {ex.Message}", 500);
        }
    }
    
    [HttpPost("delete_tag")]
    [Authorize]
    public async Task<ActionResult<BaseResult<bool>>> DeleteTag([FromBody] int id)
    {
        try
        {
            var result = await tagService.DeleteTagAsync(id);
            return Success(result, "标签删除成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到要删除的标签", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"删除标签失败: {ex.Message}", 500);
        }
    }
}
