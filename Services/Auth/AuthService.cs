using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Foxel.Models.DataBase;
using Foxel.Models.Request.Auth;
using Foxel.Services.Configuration;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using static Foxel.Utils.AuthHelper;

namespace Foxel.Services.Auth;

public class AuthService(
    IDbContextFactory<MyDbContext> dbContextFactory,
    IConfigService configuration,
    ILogger<AuthService> logger)
    : IAuthService
{
    public async Task<(bool success, string message, User? user)> RegisterUserAsync(RegisterRequest request)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        var existingUser = await context.Users.FirstOrDefaultAsync(u => u.Email == request.Email);
        if (existingUser != null)
        {
            return (false, "该邮箱已被注册", null);
        }

        existingUser = await context.Users.FirstOrDefaultAsync(u => u.UserName == request.UserName);
        if (existingUser != null)
        {
            return (false, "该用户名已被使用", null);
        }

        var user = new User
        {
            UserName = request.UserName,
            Email = request.Email,
            PasswordHash = HashPassword(request.Password),
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
            RoleId = 2,
            Role = null,
        };
        var userCount = await context.Users.CountAsync();
        if (userCount == 0)
        {
            var role = await context.Roles.FirstOrDefaultAsync(r => r.Name == "Administrator");
            user.RoleId = 1;
            user.Role = role;
        }

        context.Users.Add(user);
        await context.SaveChangesAsync();
        return (true, "用户注册成功", user);
    }

    public async Task<(bool success, string message, User? user)> AuthenticateUserAsync(LoginRequest request)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        var user = await context.Users.Include(x => x.Role).FirstOrDefaultAsync(u => u.Email == request.Email);

        if (user == null)
        {
            return (false, "用户不存在", null);
        }

        if (!VerifyPassword(request.Password, user.PasswordHash))
        {
            return (false, "密码错误", null);
        }

        return (true, "登录成功", user);
    }

    public Task<string> GenerateJwtTokenAsync(User user)
    {
        var claims = new List<Claim>
        {
            new(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new(ClaimTypes.Email, user.Email),
            new(ClaimTypes.Name, user.UserName)
        };
        if (user.Role != null)
        {
            claims.Add(new Claim(ClaimTypes.Role, user.Role.Name));
        }

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(configuration["Jwt:SecretKey"] ??
                                                                  throw new InvalidOperationException(
                                                                      "JWT Secret key not found")));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var expires = DateTime.UtcNow.AddYears(1);
        var token = new JwtSecurityToken(
            issuer: configuration["Jwt:Issuer"],
            audience: configuration["Jwt:Audience"],
            claims: claims,
            expires: expires,
            signingCredentials: creds
        );

        var tokenString = new JwtSecurityTokenHandler().WriteToken(token);
        return Task.FromResult(tokenString);
    }

    public async Task<User?> GetUserByIdAsync(int userId)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        return await context.Users.Include(x => x.Role).FirstOrDefaultAsync(u => u.Id == userId);
    }

    public async Task<(bool success, string message, User? user)> FindGitHubUserAsync(string githubId)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        var user = await context.Users.Include(x => x.Role).FirstOrDefaultAsync(u => u.GithubId == githubId);

        if (user == null)
        {
            return (false, "未找到对应的GitHub用户", null);
        }

        return (true, "找到GitHub用户", user);
    }

    public async Task<(bool success, string message, User? user)> FindLinuxDoUserAsync(string linuxdoId)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        var user = await context.Users.Include(x => x.Role).FirstOrDefaultAsync(u => u.LinuxDoId == linuxdoId);

        if (user == null)
        {
            return (false, "未找到对应的LinuxDo用户", null);
        }

        return (true, "找到LinuxDo用户", user);
    }

    public async Task<(bool success, string message, User? user)> UpdateUserInfoAsync(int userId,
        UpdateUserRequest request)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();
        var user = await context.Users.Include(x => x.Role).FirstOrDefaultAsync(u => u.Id == userId);

        if (user == null)
        {
            return (false, "用户不存在", null);
        }

        // 检查用户名是否已存在
        if (!string.IsNullOrEmpty(request.UserName) && request.UserName != user.UserName)
        {
            var existingUserName = await context.Users.AnyAsync(u => u.UserName == request.UserName);
            if (existingUserName)
            {
                return (false, "该用户名已被使用", null);
            }

            user.UserName = request.UserName;
        }

        // 检查邮箱是否已存在
        if (!string.IsNullOrEmpty(request.Email) && request.Email != user.Email)
        {
            var existingEmail = await context.Users.AnyAsync(u => u.Email == request.Email);
            if (existingEmail)
            {
                return (false, "该邮箱已被注册", null);
            }

            user.Email = request.Email;
        }

        // 如果要修改密码，验证当前密码
        if (!string.IsNullOrEmpty(request.NewPassword))
        {
            if (string.IsNullOrEmpty(request.CurrentPassword))
            {
                return (false, "需要提供当前密码", null);
            }

            if (!VerifyPassword(request.CurrentPassword, user.PasswordHash))
            {
                return (false, "当前密码不正确", null);
            }

            user.PasswordHash = HashPassword(request.NewPassword);
        }

        user.UpdatedAt = DateTime.UtcNow;
        await context.SaveChangesAsync();

        return (true, "用户信息更新成功", user);
    }

    public string GetGitHubLoginUrl()
    {
        string githubClientId = configuration["Authentication:GitHubClientId"];
        string githubCallback = configuration["Authentication:GitHubCallbackUrl"];
        return
            $"https://github.com/login/oauth/authorize?client_id={Uri.EscapeDataString(githubClientId)}&redirect_uri={Uri.EscapeDataString(githubCallback)}";
    }

    public async Task<(OAuthResult result, string message, string? data)> ProcessGitHubCallbackAsync(string code)
    {
        if (string.IsNullOrEmpty(code))
        {
            return (OAuthResult.InvalidCode, "GitHub授权码无效", null);
        }

        string githubClientId = configuration["Authentication:GitHubClientId"];
        string githubClientSecret = configuration["Authentication:GitHubClientSecret"];
        string githubTokenUrl = "https://github.com/login/oauth/access_token";
        string githubUserApiUrl = "https://api.github.com/user";

        using var httpClient = new HttpClient();
        httpClient.DefaultRequestHeaders.Add("User-Agent", "Foxel");
        httpClient.DefaultRequestHeaders.Add("Accept", "application/json");
        var tokenRequestUrl =
            $"{githubTokenUrl}?client_id={Uri.EscapeDataString(githubClientId)}&client_secret={Uri.EscapeDataString(githubClientSecret)}&code={Uri.EscapeDataString(code)}";
        var tokenResponse = await httpClient.PostAsync(tokenRequestUrl, null);

        if (!tokenResponse.IsSuccessStatusCode)
        {
            var errorContent = await tokenResponse.Content.ReadAsStringAsync();
            logger.LogError("获取GitHub访问令牌失败: {StatusCode}, {ErrorContent}", tokenResponse.StatusCode, errorContent);
            return (OAuthResult.TokenRequestFailed, $"获取GitHub访问令牌失败: {errorContent}", null);
        }

        var tokenResponseContent = await tokenResponse.Content.ReadAsStringAsync();
        var tokenJson = System.Text.Json.JsonDocument.Parse(tokenResponseContent);

        if (!tokenJson.RootElement.TryGetProperty("access_token", out var accessTokenElement) ||
            accessTokenElement.GetString() == null)
        {
            logger.LogError("GitHub响应中未找到access_token: {TokenResponseContent}", tokenResponseContent);
            return (OAuthResult.TokenRequestFailed, "获取GitHub访问令牌失败，响应中未包含令牌。", null);
        }

        var accessToken = accessTokenElement.GetString();

        httpClient.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", accessToken);

        var userResponse = await httpClient.GetAsync(githubUserApiUrl);
        if (!userResponse.IsSuccessStatusCode)
        {
            var errorContent = await userResponse.Content.ReadAsStringAsync();
            logger.LogError("获取GitHub用户信息失败: {StatusCode}, {ErrorContent}", userResponse.StatusCode, errorContent);
            return (OAuthResult.UserInfoFailed, $"获取GitHub用户信息失败: {errorContent}", null);
        }

        var userContent = await userResponse.Content.ReadAsStringAsync();
        var userJson = System.Text.Json.JsonDocument.Parse(userContent);

        string? githubUserId = null;
        string? email = null;
        string? name = null;
        string? loginName = null;

        if (userJson.RootElement.TryGetProperty("id", out var idElement))
        {
            githubUserId = idElement.GetInt64().ToString();
        }

        if (userJson.RootElement.TryGetProperty("email", out var emailElement))
        {
            email = emailElement.GetString();
        }

        if (userJson.RootElement.TryGetProperty("name", out var nameElement))
        {
            name = nameElement.GetString();
        }

        if (userJson.RootElement.TryGetProperty("login", out var loginElement))
        {
            loginName = loginElement.GetString();
        }

        if (string.IsNullOrEmpty(githubUserId))
        {
            return (OAuthResult.InvalidUserId, "无法从GitHub获取用户ID", null);
        }

        var (isSuccess, message, user) = await FindGitHubUserAsync(githubUserId);

        if (!isSuccess || user == null)
        {
            return (OAuthResult.UserNotBound, "GitHub用户未绑定到系统账户", githubUserId);
        }

        var jwtToken = await GenerateJwtTokenAsync(user);
        return (OAuthResult.Success, "GitHub授权成功", jwtToken);
    }

    public string GetLinuxDoLoginUrl()
    {
        string linuxdoClientId = configuration["Authentication:LinuxDoClientId"];
        string linuxdoCallback = configuration["Authentication:LinuxDoCallbackUrl"];
        string state = Guid.NewGuid().ToString();
        return
            $"https://connect.linux.do/oauth2/authorize?response_type=code&client_id={Uri.EscapeDataString(linuxdoClientId)}&redirect_uri={Uri.EscapeDataString(linuxdoCallback)}&state={Uri.EscapeDataString(state)}";
    }

    public async Task<(OAuthResult result, string message, string? data)> ProcessLinuxDoCallbackAsync(string code)
    {
        if (string.IsNullOrEmpty(code))
        {
            return (OAuthResult.InvalidCode, "LinuxDo授权码无效", null);
        }

        string linuxdoClientId = configuration["Authentication:LinuxDoClientId"];
        string linuxdoClientSecret = configuration["Authentication:LinuxDoClientSecret"];
        string linuxdoCallback = configuration["Authentication:LinuxDoCallbackUrl"];
        string linuxdoTokenUrl = "https://connect.linux.do/oauth2/token";
        string linuxdoUserApiUrl = "https://connect.linux.do/api/user";

        using var httpClient = new HttpClient();
        httpClient.DefaultRequestHeaders.Add("User-Agent", "Foxel");

        // 构建 token 请求参数
        var tokenParams = new List<KeyValuePair<string, string>>
        {
            new("grant_type", "authorization_code"),
            new("client_id", linuxdoClientId),
            new("client_secret", linuxdoClientSecret),
            new("code", code),
            new("redirect_uri", linuxdoCallback)
        };

        var tokenContent = new FormUrlEncodedContent(tokenParams);
        var tokenResponse = await httpClient.PostAsync(linuxdoTokenUrl, tokenContent);

        if (!tokenResponse.IsSuccessStatusCode)
        {
            var errorContent = await tokenResponse.Content.ReadAsStringAsync();
            logger.LogError("获取LinuxDo访问令牌失败: {StatusCode}, {ErrorContent}", tokenResponse.StatusCode, errorContent);
            return (OAuthResult.TokenRequestFailed, $"获取LinuxDo访问令牌失败: {errorContent}", null);
        }

        var tokenResponseContent = await tokenResponse.Content.ReadAsStringAsync();
        var tokenJson = System.Text.Json.JsonDocument.Parse(tokenResponseContent);

        if (!tokenJson.RootElement.TryGetProperty("access_token", out var accessTokenElement) ||
            accessTokenElement.GetString() == null)
        {
            logger.LogError("LinuxDo响应中未找到access_token: {TokenResponseContent}", tokenResponseContent);
            return (OAuthResult.TokenRequestFailed, "获取LinuxDo访问令牌失败，响应中未包含令牌。", null);
        }

        var accessToken = accessTokenElement.GetString();

        // 获取用户信息
        httpClient.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", accessToken);

        var userResponse = await httpClient.GetAsync(linuxdoUserApiUrl);
        if (!userResponse.IsSuccessStatusCode)
        {
            var errorContent = await userResponse.Content.ReadAsStringAsync();
            logger.LogError("获取LinuxDo用户信息失败: {StatusCode}, {ErrorContent}", userResponse.StatusCode, errorContent);
            return (OAuthResult.UserInfoFailed, $"获取LinuxDo用户信息失败: {errorContent}", null);
        }

        var userContent = await userResponse.Content.ReadAsStringAsync();
        var userJson = System.Text.Json.JsonDocument.Parse(userContent);

        string? linuxdoUserId = null;
        string? email = null;
        string? username = null;

        if (userJson.RootElement.TryGetProperty("id", out var idElement))
        {
            linuxdoUserId = idElement.GetInt32().ToString();
        }

        if (userJson.RootElement.TryGetProperty("email", out var emailElement))
        {
            email = emailElement.GetString();
        }

        if (userJson.RootElement.TryGetProperty("username", out var usernameElement))
        {
            username = usernameElement.GetString();
        }

        if (string.IsNullOrEmpty(linuxdoUserId))
        {
            return (OAuthResult.InvalidUserId, "无法从LinuxDo获取用户ID", null);
        }

        var (isSuccess, message, user) = await FindLinuxDoUserAsync(linuxdoUserId);

        if (!isSuccess || user == null)
        {
            return (OAuthResult.UserNotBound, "LinuxDo用户未绑定到系统账户", linuxdoUserId);
        }

        var jwtToken = await GenerateJwtTokenAsync(user);
        return (OAuthResult.Success, "LinuxDo授权成功", jwtToken);
    }

    public async Task<(bool success, string message, User? user)> BindAccountAsync(BindAccountRequest request)
    {
        await using var context = await dbContextFactory.CreateDbContextAsync();

        // 检查第三方ID是否已被绑定
        User? existingThirdPartyUser = null;
        if (request.BindType == BindType.GitHub)
        {
            existingThirdPartyUser = await context.Users.Include(x => x.Role)
                .FirstOrDefaultAsync(u => u.GithubId == request.ThirdPartyUserId);
        }
        else if (request.BindType == BindType.LinuxDo)
        {
            existingThirdPartyUser = await context.Users.Include(x => x.Role)
                .FirstOrDefaultAsync(u => u.LinuxDoId == request.ThirdPartyUserId);
        }

        if (existingThirdPartyUser != null)
        {
            return (false, $"该{request.BindType}账户已被绑定", null);
        }

        // 查找邮箱对应的用户
        var existingUser = await context.Users.Include(x => x.Role)
            .FirstOrDefaultAsync(u => u.Email == request.Email);

        if (existingUser != null)
        {
            // 验证密码
            if (!VerifyPassword(request.Password, existingUser.PasswordHash))
            {
                return (false, "密码错误", null);
            }

            // 检查是否已绑定对应类型的第三方账户
            if (request.BindType == BindType.GitHub && !string.IsNullOrEmpty(existingUser.GithubId))
            {
                return (false, "该账户已绑定GitHub", null);
            }

            if (request.BindType == BindType.LinuxDo && !string.IsNullOrEmpty(existingUser.LinuxDoId))
            {
                return (false, "该账户已绑定LinuxDo", null);
            }

            // 绑定第三方账户
            if (request.BindType == BindType.GitHub)
            {
                existingUser.GithubId = request.ThirdPartyUserId;
            }
            else if (request.BindType == BindType.LinuxDo)
            {
                existingUser.LinuxDoId = request.ThirdPartyUserId;
            }

            existingUser.UpdatedAt = DateTime.UtcNow;
            await context.SaveChangesAsync();

            return (true, $"{request.BindType}账户绑定成功", existingUser);
        }
        else
        {
            // 用户不存在，创建新用户并绑定第三方账户
            var newUser = new User
            {
                UserName = request.Email.Split('@')[0], // 使用邮箱前缀作为用户名
                Email = request.Email,
                PasswordHash = HashPassword(request.Password),
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow,
                RoleId = 2, // 默认用户角色
                Role = null,
            };

            // 绑定第三方账户
            if (request.BindType == BindType.GitHub)
            {
                newUser.GithubId = request.ThirdPartyUserId;
            }
            else if (request.BindType == BindType.LinuxDo)
            {
                newUser.LinuxDoId = request.ThirdPartyUserId;
            }

            // 如果是第一个用户，设置为管理员
            var userCount = await context.Users.CountAsync();
            if (userCount == 0)
            {
                var role = await context.Roles.FirstOrDefaultAsync(r => r.Name == "Administrator");
                newUser.RoleId = 1;
                newUser.Role = role;
            }

            context.Users.Add(newUser);
            await context.SaveChangesAsync();

            return (true, $"账户注册并绑定{request.BindType}成功", newUser);
        }
    }
}