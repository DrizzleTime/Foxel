using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Foxel.Models;
using Foxel.Models.Request.User;
using Foxel.Models.Response.User;
using Foxel.Services.Management;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/user")]
public class UserManagementController(IUserManagementService userManagementService) : BaseApiController
{
    [HttpGet("get_users")]
    public async Task<ActionResult<PaginatedResult<UserResponse>>> GetUsers(
        [FromQuery] int page = 1, 
        [FromQuery] int pageSize = 10,
        [FromQuery] string? searchQuery = null,
        [FromQuery] string? role = null,
        [FromQuery] DateTime? startDate = null,
        [FromQuery] DateTime? endDate = null)
    {
        try
        {
            DateTime? utcStartDate = null;
            DateTime? utcEndDate = null;

            if (startDate.HasValue)
            {
                utcStartDate = startDate.Value.Kind == DateTimeKind.Utc 
                    ? startDate.Value 
                    : DateTime.SpecifyKind(startDate.Value, DateTimeKind.Utc);
            }

            if (endDate.HasValue)
            {
                utcEndDate = endDate.Value.Kind == DateTimeKind.Utc 
                    ? endDate.Value 
                    : DateTime.SpecifyKind(endDate.Value, DateTimeKind.Utc);
            }

            var users = await userManagementService.GetUsersAsync(page, pageSize, searchQuery, role, utcStartDate, utcEndDate);
            return PaginatedSuccess(users.Data, users.TotalCount, users.Page, users.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<UserResponse>($"获取用户列表失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_user/{id}")]
    public async Task<ActionResult<BaseResult<UserResponse>>> GetUserById(int id)
    {
        try
        {
            var user = await userManagementService.GetUserByIdAsync(id);
            return Success(user, "用户获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<UserResponse>("找不到指定用户", 404);
        }
        catch (Exception ex)
        {
            return Error<UserResponse>($"获取用户失败: {ex.Message}", 500);
        }
    }

    [HttpPost("create_user")]
    public async Task<ActionResult<BaseResult<UserResponse>>> CreateUser([FromBody] CreateUserRequest request)
    {
        try
        {
            var user = await userManagementService.CreateUserAsync(request.UserName, request.Email, request.Password, request.Role);
            return Success(user, "用户创建成功");
        }
        catch (ArgumentException ex)
        {
            return Error<UserResponse>(ex.Message);
        }
        catch (Exception ex)
        {
            return Error<UserResponse>($"创建用户失败: {ex.Message}", 500);
        }
    }

    [HttpPost("update_user")]
    public async Task<ActionResult<BaseResult<UserResponse>>> UpdateUser([FromBody] UpdateUserRequest request)
    {
        try
        {
            var user = await userManagementService.UpdateUserAsync(request.Id, request.UserName, request.Email, request.Role);
            return Success(user, "用户更新成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<UserResponse>("找不到要更新的用户", 404);
        }
        catch (ArgumentException ex)
        {
            return Error<UserResponse>(ex.Message);
        }
        catch (Exception ex)
        {
            return Error<UserResponse>($"更新用户失败: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_user")]
    public async Task<ActionResult<BaseResult<bool>>> DeleteUser([FromBody] int id)
    {
        try
        {
            var result = await userManagementService.DeleteUserAsync(id);
            return Success(result, "用户删除成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到要删除的用户", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"删除用户失败: {ex.Message}", 500);
        }
    }

    [HttpPost("batch_delete_users")]
    public async Task<ActionResult<BaseResult<BatchDeleteResult>>> BatchDeleteUsers([FromBody] List<int> ids)
    {
        try
        {
            if (ids.Count == 0)
            {
                return Error<BatchDeleteResult>("未提供用户ID");
            }

            var result = await userManagementService.BatchDeleteUsersAsync(ids);
            return Success(result, $"成功删除 {result.SuccessCount} 个用户，失败 {result.FailedCount} 个");
        }
        catch (Exception ex)
        {
            return Error<BatchDeleteResult>($"批量删除用户失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_user_detail/{id}")]
    public async Task<ActionResult<BaseResult<UserDetailResponse>>> GetUserDetail(int id)
    {
        try
        {
            var userDetail = await userManagementService.GetUserDetailAsync(id);
            return Success(userDetail, "用户详情获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<UserDetailResponse>("找不到指定用户", 404);
        }
        catch (Exception ex)
        {
            return Error<UserDetailResponse>($"获取用户详情失败: {ex.Message}", 500);
        }
    }
}