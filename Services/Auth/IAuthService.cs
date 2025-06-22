using Foxel.Models.DataBase;
using Foxel.Models.Request.Auth;

namespace Foxel.Services.Auth;

public enum OAuthResult
{
    Success,
    UserNotBound,
    InvalidCode,
    TokenRequestFailed,
    UserInfoFailed,
    InvalidUserId
}

public interface IAuthService
{
    Task<(bool success, string message, User? user)> RegisterUserAsync(RegisterRequest request);
    Task<(bool success, string message, User? user)> AuthenticateUserAsync(LoginRequest request);
    Task<string> GenerateJwtTokenAsync(User user);
    Task<User?> GetUserByIdAsync(int userId);
    Task<(bool success, string message, User? user)> FindGitHubUserAsync(string githubId);
    Task<(bool success, string message, User? user)> FindLinuxDoUserAsync(string linuxdoId);
    Task<(bool success, string message, User? user)> UpdateUserInfoAsync(int userId, UpdateUserRequest request);
    string GetGitHubLoginUrl();
    string GetLinuxDoLoginUrl();
    Task<(OAuthResult result, string message, string? data)> ProcessGitHubCallbackAsync(string code);
    Task<(OAuthResult result, string message, string? data)> ProcessLinuxDoCallbackAsync(string code);
    Task<(bool success, string message, User? user)> BindAccountAsync(BindAccountRequest request);
}