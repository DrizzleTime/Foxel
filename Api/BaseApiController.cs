using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using Foxel.Models;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api
{
    [ApiController]
    [Route("api/[controller]")]
    public abstract class BaseApiController : ControllerBase
    {
        protected int? GetCurrentUserId()
        {
            var userIdClaim = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            return userIdClaim != null ? int.Parse(userIdClaim) : null;
        }

        protected int? GetUserIdFromCookie()
        {
            try
            {
                var token = Request.Cookies["token"];
                if (string.IsNullOrEmpty(token))
                {
                    return null;
                }

                var tokenHandler = new JwtSecurityTokenHandler();
                if (!tokenHandler.CanReadToken(token))
                {
                    return null;
                }

                var jwtToken = tokenHandler.ReadJwtToken(token);
                var userIdClaim = jwtToken.Claims.FirstOrDefault(x => x.Type == ClaimTypes.NameIdentifier)?.Value;
                if (userIdClaim != null && int.TryParse(userIdClaim, out var userId))
                {
                    return userId;
                }
            }
            catch (Exception)
            {
                return null;
            }

            return null;
        }

        protected ActionResult<BaseResult<T>> Success<T>(T data, string message = "操作成功", int statusCode = 200)
        {
            return Ok(new BaseResult<T>
            {
                Success = true,
                Message = message,
                Data = data,
                StatusCode = statusCode
            });
        }

        protected ActionResult<BaseResult<T>> Success<T>(string message = "操作成功", int statusCode = 200)
        {
            return Ok(new BaseResult<T>
            {
                Success = true,
                Message = message,
                StatusCode = statusCode
            });
        }

        protected ActionResult<BaseResult<T>> Error<T>(string message, int statusCode = 400)
        {
            return StatusCode(statusCode, new BaseResult<T>
            {
                Success = false,
                Message = message,
                StatusCode = statusCode
            });
        }

        protected ActionResult<PaginatedResult<T>> PaginatedSuccess<T>(
            List<T>? data,
            int totalCount,
            int page,
            int pageSize,
            string message = "获取成功")
        {
            return Ok(new PaginatedResult<T>
            {
                Success = true,
                Message = message,
                Data = data,
                TotalCount = totalCount,
                Page = page,
                PageSize = pageSize,
                StatusCode = 200
            });
        }

        protected ActionResult<PaginatedResult<T>> PaginatedError<T>(string message, int statusCode = 400)
        {
            return StatusCode(statusCode, new PaginatedResult<T>
            {
                Success = false,
                Message = message,
                Data = new List<T>(),
                TotalCount = 0,
                Page = 0,
                PageSize = 0,
                StatusCode = statusCode
            });
        }
    }
}