using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Foxel.Models;
using Foxel.Services.VectorDb;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/system")]
public class SystemManagementController(IVectorDbService vectorDbService) : BaseApiController
{
    private readonly VectorDbManager _vectorDbManager = (VectorDbManager)vectorDbService;

    [HttpPost("vector-db/switch")]
    public async Task<ActionResult<BaseResult<bool>>> SwitchVectorDb([FromBody] SwitchVectorDbRequest request)
    {
        try
        {
            // 将字符串转换为枚举类型（如果需要）
            if (Enum.TryParse<VectorDbType>(request.Type, out var dbType))
            {
                await _vectorDbManager.SwitchVectorDbAsync(dbType);
                return Success(true, $"已切换到 {request.Type} 向量数据库");
            }
            else
            {
                return Error<bool>($"无效的向量数据库类型: {request.Type}", 400);
            }
        }
        catch (Exception ex)
        {
            return Error<bool>($"切换向量数据库失败: {ex.Message}", 500);
        }
    }

    [HttpGet("vector-db/current")]
    public ActionResult<BaseResult<VectorDbInfo>> GetCurrentVectorDb()
    {
        try
        {
            var currentType = _vectorDbManager.GetCurrentVectorDbType();
            var info = new VectorDbInfo { Type = currentType.ToString() };
            return Success(info, "获取当前向量数据库类型成功");
        }
        catch (Exception ex)
        {
            return Error<VectorDbInfo>($"获取当前向量数据库类型失败: {ex.Message}", 500);
        }
    }

    [HttpDelete("vector-db/clear")]
    public async Task<ActionResult<BaseResult<bool>>> ClearVectors()
    {
        try
        {
            await _vectorDbManager.ClearVectorsAsync();
            return Success(true, "向量数据库清空成功");
        }
        catch (Exception ex)
        {
            return Error<bool>($"清空向量数据库失败: {ex.Message}", 500);
        }
    }

    [HttpPost("vector-db/rebuild")]
    public async Task<ActionResult<BaseResult<bool>>> RebuildVectors()
    {
        try
        {
            await _vectorDbManager.ClearVectorsAsync();
            _ = _vectorDbManager.BuildUserPictureVectorsAsync();
            return Success(true, "向量数据库重建中，请稍后检查状态");
        }
        catch (Exception ex)
        {
            return Error<bool>($"重建向量数据库失败: {ex.Message}", 500);
        }
    }
}

public class SwitchVectorDbRequest
{
    public string Type { get; set; } = string.Empty;
}

public class VectorDbInfo
{
    public string Type { get; set; } = string.Empty;
}
