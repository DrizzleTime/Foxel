using Foxel.Models;
using Foxel.Models.Response.Face;
using Foxel.Models.Response.Picture;
using Foxel.Services.AI;
using Foxel.Services.Management;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api;

[Authorize]
[Route("api/face")]
public class FaceController(
    IFaceManagementService faceManagementService,
    IFaceClusteringService faceClusteringService,
    ILogger<FaceController> logger) : BaseApiController
{
    /// <summary>
    /// 获取当前用户的人脸聚类列表
    /// </summary>
    [HttpGet("clusters")]
    public async Task<ActionResult<BaseResult<PaginatedResult<FaceClusterResponse>>>> GetMyFaceClusters(
        [FromQuery] int page = 1, [FromQuery] int pageSize = 20)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<PaginatedResult<FaceClusterResponse>>("用户未认证", 401);

            var result = await faceManagementService.GetUserFaceClustersAsync(userId.Value, page, pageSize);
            return Success(result, "获取人脸聚类列表成功");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "获取用户人脸聚类列表失败: UserId={UserId}", GetCurrentUserId());
            return Error<PaginatedResult<FaceClusterResponse>>("获取人脸聚类列表失败", 500);
        }
    }

    /// <summary>
    /// 根据聚类获取当前用户的图片
    /// </summary>
    [HttpGet("clusters/{clusterId}/pictures")]
    public async Task<ActionResult<BaseResult<PaginatedResult<PictureResponse>>>> GetMyPicturesByCluster(
        int clusterId, [FromQuery] int page = 1, [FromQuery] int pageSize = 20)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<PaginatedResult<PictureResponse>>("用户未认证", 401);

            var result = await faceManagementService.GetUserPicturesByClusterAsync(
                userId.Value, clusterId, page, pageSize);
            return Success(result, "获取聚类图片成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<PaginatedResult<PictureResponse>>("找不到指定的人脸聚类或无权访问", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "获取用户聚类图片失败: UserId={UserId}, ClusterId={ClusterId}", 
                GetCurrentUserId(), clusterId);
            return Error<PaginatedResult<PictureResponse>>("获取聚类图片失败", 500);
        }
    }

    /// <summary>
    /// 更新当前用户的人脸聚类信息
    /// </summary>
    [HttpPut("clusters/{clusterId}")]
    public async Task<ActionResult<BaseResult<FaceClusterResponse>>> UpdateMyCluster(
        int clusterId, [FromBody] UpdateClusterRequest request)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<FaceClusterResponse>("用户未认证", 401);

            var result = await faceManagementService.UpdateUserClusterAsync(
                userId.Value, clusterId, request.PersonName, request.Description);
            return Success(result, "更新聚类信息成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<FaceClusterResponse>("找不到指定的人脸聚类或无权访问", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "更新用户聚类信息失败: UserId={UserId}, ClusterId={ClusterId}", 
                GetCurrentUserId(), clusterId);
            return Error<FaceClusterResponse>("更新聚类信息失败", 500);
        }
    }

    /// <summary>
    /// 开始当前用户的人脸聚类
    /// </summary>
    [HttpPost("clusters/analyze")]
    public async Task<ActionResult<BaseResult<bool>>> StartMyFaceClustering()
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<bool>("用户未认证", 401);

            await faceClusteringService.ClusterUserFacesAsync(userId.Value);
            return Success(true, "人脸聚类任务已开始");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "启动用户人脸聚类失败: UserId={UserId}", GetCurrentUserId());
            return Error<bool>("启动人脸聚类失败", 500);
        }
    }

    /// <summary>
    /// 合并当前用户的聚类
    /// </summary>
    [HttpPost("clusters/{targetClusterId}/merge")]
    public async Task<ActionResult<BaseResult<bool>>> MergeMyUserClusters(
        int targetClusterId, [FromBody] MergeClustersRequest request)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<bool>("用户未认证", 401);

            var result = await faceManagementService.MergeUserClustersAsync(
                userId.Value, request.SourceClusterId, targetClusterId);
            return Success(result, "合并聚类成功");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>(ex.Message, 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "合并用户聚类失败: UserId={UserId}", GetCurrentUserId());
            return Error<bool>("合并聚类失败", 500);
        }
    }

    /// <summary>
    /// 从聚类中移除人脸
    /// </summary>
    [HttpDelete("faces/{faceId}/cluster")]
    public async Task<ActionResult<BaseResult<bool>>> RemoveFaceFromCluster(int faceId)
    {
        try
        {
            var userId = GetCurrentUserId();
            if (!userId.HasValue)
                return Error<bool>("用户未认证", 401);

            var result = await faceManagementService.RemoveUserFaceFromClusterAsync(userId.Value, faceId);
            return Success(result, "移除人脸成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到指定的人脸或无权访问", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "移除用户人脸失败: UserId={UserId}, FaceId={FaceId}", 
                GetCurrentUserId(), faceId);
            return Error<bool>("移除人脸失败", 500);
        }
    }

}

public record UpdateClusterRequest
{
    public string? PersonName { get; set; }
    public string? Description { get; set; }
}

public record MergeClustersRequest
{
    public int SourceClusterId { get; set; }
}