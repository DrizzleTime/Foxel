using Foxel.Models;
using Foxel.Models.Request.Auth;
using Foxel.Models.Response.Auth;
using Foxel.Services.Auth;
using Foxel.Services.Configuration;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api;

[Route("api/auth")]
public class AuthController(IAuthService authService, IConfigService configuration) : BaseApiController
{
    [HttpPost("register")]
    public async Task<ActionResult<BaseResult<AuthResponse>>> Register([FromBody] RegisterRequest request)
    {
        if (!ModelState.IsValid)
        {
            return Error<AuthResponse>("请求数据无效");
        }

        // 检查是否允许新用户注册
        var enableRegistration = configuration["AppSettings:EnableRegistration"];
        if (string.Equals(enableRegistration, "false", StringComparison.OrdinalIgnoreCase))
        {
            return Error<AuthResponse>("新用户注册功能已关闭");
        }

        var (success, message, user) = await authService.RegisterUserAsync(request);
        if (!success)
        {
            return Error<AuthResponse>(message);
        }

        var token = await authService.GenerateJwtTokenAsync(user!);
        var response = new AuthResponse
        {
            Token = token,
            User = new UserProfile
            {
                Id = user!.Id,
                UserName = user.UserName,
                Email = user.Email,
                RoleName = user.Role?.Name
            }
        };

        return Success(response, "注册成功");
    }

    [HttpPost("login")]
    public async Task<ActionResult<BaseResult<AuthResponse>>> Login([FromBody] LoginRequest request)
    {
        if (!ModelState.IsValid)
        {
            return Error<AuthResponse>("请求数据无效");
        }

        var (success, message, user) = await authService.AuthenticateUserAsync(request);
        if (!success)
        {
            return Error<AuthResponse>(message, 401);
        }

        var token = await authService.GenerateJwtTokenAsync(user!);
        var response = new AuthResponse
        {
            Token = token,
            User = new UserProfile
            {
                Id = user!.Id,
                UserName = user.UserName,
                Email = user.Email,
                RoleName = user.Role?.Name
            }
        };

        return Success(response, "登录成功");
    }

    [HttpGet("get_current_user")]
    [Authorize]
    public async Task<ActionResult<BaseResult<UserProfile>>> GetCurrentUser()
    {
        var userId = GetCurrentUserId();
        if (userId == null)
        {
            return Error<UserProfile>("用户ID未找到");
        }

        var user = await authService.GetUserByIdAsync(userId.Value);
        if (user == null)
        {
            return Error<UserProfile>("未找到用户信息", 404);
        }

        var profile = new UserProfile
        {
            Id = userId.Value,
            Email = user.Email,
            UserName = user.UserName,
            RoleName = user.Role?.Name
        };

        return Success(profile);
    }

    [HttpGet("github/login")]
    public IActionResult GitHubLogin()
    {
        string githubAuthorizeUrl = authService.GetGitHubLoginUrl();
        return Redirect(githubAuthorizeUrl);
    }

    [HttpGet("github/callback")]
    public async Task<ActionResult<BaseResult<string>>> GitHubCallback(string code)
    {
        var (result, message, data) = await authService.ProcessGitHubCallbackAsync(code);

        switch (result)
        {
            case OAuthResult.Success:
                return Redirect($"/login?token={Uri.EscapeDataString(data!)}");

            case OAuthResult.UserNotBound:
                return Redirect($"/bind?githubId={data}");
            case OAuthResult.InvalidCode:
            case OAuthResult.TokenRequestFailed:
            case OAuthResult.UserInfoFailed:
            case OAuthResult.InvalidUserId:
            default:
                return Redirect($"/login?error=github_auth_failed&message={Uri.EscapeDataString(message)}");
        }
    }

    [HttpGet("linuxdo/login")]
    public IActionResult LinuxDoLogin()
    {
        string linuxdoAuthorizeUrl = authService.GetLinuxDoLoginUrl();
        return Redirect(linuxdoAuthorizeUrl);
    }

    [HttpGet("linuxdo/callback")]
    public async Task<ActionResult<BaseResult<string>>> LinuxDoCallback(string code, string state)
    {
        var (result, message, data) = await authService.ProcessLinuxDoCallbackAsync(code);

        switch (result)
        {
            case OAuthResult.Success:
                return Redirect($"/login?token={Uri.EscapeDataString(data!)}");

            case OAuthResult.UserNotBound:
                return Redirect($"/bind?linuxdoId={data}");
            case OAuthResult.InvalidCode:
            case OAuthResult.TokenRequestFailed:
            case OAuthResult.UserInfoFailed:
            case OAuthResult.InvalidUserId:
            default:
                return Redirect($"/login?error=linuxdo_auth_failed&message={Uri.EscapeDataString(message)}");
        }
    }

    [HttpPut("update")]
    [Authorize]
    public async Task<ActionResult<BaseResult<UserProfile>>> UpdateUserInfo([FromBody] UpdateUserRequest request)
    {
        if (!ModelState.IsValid)
        {
            return Error<UserProfile>("请求数据无效");
        }

        var userId = GetCurrentUserId();
        if (userId == null)
        {
            return Error<UserProfile>("用户ID未找到");
        }

        var (success, message, user) = await authService.UpdateUserInfoAsync(userId.Value, request);
        if (!success || user == null)
        {
            return Error<UserProfile>(message);
        }

        var profile = new UserProfile
        {
            Id = user.Id,
            Email = user.Email,
            UserName = user.UserName,
            RoleName = user.Role?.Name
        };

        return Success(profile, "用户信息更新成功");
    }

    [HttpPost("bind")]
    public async Task<ActionResult<BaseResult<AuthResponse>>> BindAccount([FromBody] BindAccountRequest request)
    {
        if (!ModelState.IsValid)
        {
            return Error<AuthResponse>("请求数据无效");
        }

        var (success, message, user) = await authService.BindAccountAsync(request);
        if (!success || user == null)
        {
            return Error<AuthResponse>(message);
        }

        var token = await authService.GenerateJwtTokenAsync(user);
        var response = new AuthResponse
        {
            Token = token,
            User = new UserProfile
            {
                Id = user.Id,
                UserName = user.UserName,
                Email = user.Email,
                RoleName = user.Role?.Name
            }
        };

        return Success(response, message);
    }
}