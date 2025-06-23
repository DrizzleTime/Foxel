using Foxel.Models;
using Foxel.Models.Response.User;

namespace Foxel.Services.Management;

public interface IUserManagementService
{
    Task<PaginatedResult<UserResponse>> GetUsersAsync(int page = 1, int pageSize = 10, string? searchQuery = null, string? role = null, DateTime? startDate = null, DateTime? endDate = null);
    Task<UserResponse> GetUserByIdAsync(int id);
    Task<UserDetailResponse> GetUserDetailAsync(int id);
    Task<UserResponse> CreateUserAsync(string userName, string email, string password, string role);
    Task<UserResponse> UpdateUserAsync(int id, string userName, string email, string role);
    Task<bool> DeleteUserAsync(int id);
    Task<BatchDeleteResult> BatchDeleteUsersAsync(List<int> ids);
}