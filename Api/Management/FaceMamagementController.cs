using Foxel.Models;
using Foxel.Models.Response.Face;
using Foxel.Models.Response.Picture;
using Foxel.Services.AI;
using Foxel.Services.Management;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/face")]
public class FaceManagementController(
    IFaceManagementService faceManagementService,
    IFaceClusteringService faceClusteringService,
    ILogger<FaceManagementController> logger) : BaseApiController
{
    /// <summary>
    /// 获取所有用户的人脸聚类列表
    /// </summary>
    [HttpGet("clusters")]
    public async Task<ActionResult<BaseResult<PaginatedResult<FaceClusterResponse>>>> GetAllFaceClusters(
        [FromQuery] int page = 1, [FromQuery] int pageSize = 20, [FromQuery] int? userId = null)
    {
        try
        {
            var result = userId.HasValue 
                ? await faceManagementService.GetUserFaceClustersAsync(userId.Value, page, pageSize)
                : await faceManagementService.GetFaceClustersAsync(page, pageSize);
            return Success(result, "获取人脸聚类列表成功");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员获取人脸聚类列表失败");
            return Error<PaginatedResult<FaceClusterResponse>>("获取人脸聚类列表失败", 500);
        }
    }

    /// <summary>
    /// 根据聚类获取图片（管理员可查看所有）
    /// </summary>
    [HttpGet("clusters/{clusterId}/pictures")]
    public async Task<ActionResult<BaseResult<PaginatedResult<PictureResponse>>>> GetPicturesByCluster(
        int clusterId, [FromQuery] int page = 1, [FromQuery] int pageSize = 20)
    {
        try
        {
            var result = await faceManagementService.GetPicturesByClusterAsync(clusterId, page, pageSize);
            return Success(result, "获取聚类图片成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<PaginatedResult<PictureResponse>>("找不到指定的人脸聚类", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员获取聚类图片失败: ClusterId={ClusterId}", clusterId);
            return Error<PaginatedResult<PictureResponse>>("获取聚类图片失败", 500);
        }
    }

    /// <summary>
    /// 更新人脸聚类信息（管理员）
    /// </summary>
    [HttpPut("clusters/{clusterId}")]
    public async Task<ActionResult<BaseResult<FaceClusterResponse>>> UpdateCluster(
        int clusterId, [FromBody] UpdateClusterRequest request)
    {
        try
        {
            var result = await faceManagementService.UpdateClusterAsync(
                clusterId, request.PersonName, request.Description);
            return Success(result, "更新聚类信息成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<FaceClusterResponse>("找不到指定的人脸聚类", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员更新聚类信息失败: ClusterId={ClusterId}", clusterId);
            return Error<FaceClusterResponse>("更新聚类信息失败", 500);
        }
    }

    /// <summary>
    /// 开始全局人脸聚类（管理员）
    /// </summary>
    [HttpPost("clusters/analyze")]
    public async Task<ActionResult<BaseResult<bool>>> StartGlobalFaceClustering([FromQuery] int? userId = null)
    {
        try
        {
            if (userId.HasValue)
            {
                await faceClusteringService.ClusterUserFacesAsync(userId.Value);
            }
            else
            {
                await faceClusteringService.ClusterFacesAsync();
            }
            return Success(true, "人脸聚类任务已开始");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员启动人脸聚类失败");
            return Error<bool>("启动人脸聚类失败", 500);
        }
    }

    /// <summary>
    /// 合并聚类（管理员）
    /// </summary>
    [HttpPost("clusters/{targetClusterId}/merge")]
    public async Task<ActionResult<BaseResult<bool>>> MergeClusters(
        int targetClusterId, [FromBody] MergeClustersRequest request)
    {
        try
        {
            var result = await faceManagementService.MergeClustersAsync(
                request.SourceClusterId, targetClusterId);
            return Success(result, "合并聚类成功");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>(ex.Message, 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员合并聚类失败");
            return Error<bool>("合并聚类失败", 500);
        }
    }

    /// <summary>
    /// 删除聚类（管理员）
    /// </summary>
    [HttpDelete("clusters/{clusterId}")]
    public async Task<ActionResult<BaseResult<bool>>> DeleteCluster(int clusterId)
    {
        try
        {
            var result = await faceManagementService.DeleteClusterAsync(clusterId);
            return Success(result, "删除聚类成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到指定的人脸聚类", 404);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员删除聚类失败: ClusterId={ClusterId}", clusterId);
            return Error<bool>("删除聚类失败", 500);
        }
    }

    /// <summary>
    /// 从聚类中移除人脸（管理员）
    /// </summary>
    [HttpDelete("faces/{faceId}/cluster")]
    public async Task<ActionResult<BaseResult<bool>>> RemoveFaceFromCluster(int faceId)
    {
        try
        {
            var result = await faceManagementService.RemoveFaceFromClusterAsync(faceId);
            return Success(result, "移除人脸成功");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "管理员移除人脸失败: FaceId={FaceId}", faceId);
            return Error<bool>("移除人脸失败", 500);
        }
    }

    /// <summary>
    /// 获取人脸聚类统计信息
    /// </summary>
    [HttpGet("statistics")]
    public async Task<ActionResult<BaseResult<FaceClusterStatistics>>> GetClusterStatistics()
    {
        try
        {
            var result = await faceManagementService.GetClusterStatisticsAsync();
            return Success(result, "获取统计信息成功");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "获取聚类统计信息失败");
            return Error<FaceClusterStatistics>("获取统计信息失败", 500);
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

public record FaceClusterStatistics
{
    public int TotalClusters { get; set; }
    public int TotalFaces { get; set; }
    public int UnclusteredFaces { get; set; }
    public int NamedClusters { get; set; }
    public Dictionary<int, int> ClustersByUser { get; set; } = new();
}
