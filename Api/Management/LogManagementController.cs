using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Foxel.Models;
using Foxel.Models.Response.Log;
using Foxel.Models.Request.Log;
using Foxel.Services.Management;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/log")]
public class LogManagementController(ILogManagementService logManagementService) : BaseApiController
{
    [HttpGet("get_logs")]
    public async Task<ActionResult<PaginatedResult<LogResponse>>> GetLogs(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 10,
        [FromQuery] string? searchQuery = null,
        [FromQuery] LogLevel? level = null,
        [FromQuery] DateTime? startDate = null,
        [FromQuery] DateTime? endDate = null)
    {
        try
        {
            var logs = await logManagementService.GetLogsAsync(page, pageSize, searchQuery, level, startDate, endDate);
            return PaginatedSuccess(logs.Data, logs.TotalCount, logs.Page, logs.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<LogResponse>($"获取日志列表失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_log/{id}")]
    public async Task<ActionResult<BaseResult<LogResponse>>> GetLogById(int id)
    {
        try
        {
            var log = await logManagementService.GetLogByIdAsync(id);
            return Success(log, "日志获取成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<LogResponse>("找不到指定日志", 404);
        }
        catch (Exception ex)
        {
            return Error<LogResponse>($"获取日志失败: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_log")]
    public async Task<ActionResult<BaseResult<bool>>> DeleteLog([FromBody] int id)
    {
        try
        {
            var result = await logManagementService.DeleteLogAsync(id);
            return Success(result, "日志删除成功");
        }
        catch (KeyNotFoundException)
        {
            return Error<bool>("找不到要删除的日志", 404);
        }
        catch (Exception ex)
        {
            return Error<bool>($"删除日志失败: {ex.Message}", 500);
        }
    }

    [HttpPost("batch_delete_logs")]
    public async Task<ActionResult<BaseResult<BatchDeleteResult>>> BatchDeleteLogs([FromBody] List<int> ids)
    {
        try
        {
            if (ids.Count == 0)
            {
                return Error<BatchDeleteResult>("未提供日志ID");
            }

            var result = await logManagementService.BatchDeleteLogsAsync(ids);
            return Success(result, $"成功删除 {result.SuccessCount} 条日志，失败 {result.FailedCount} 条");
        }
        catch (Exception ex)
        {
            return Error<BatchDeleteResult>($"批量删除日志失败: {ex.Message}", 500);
        }
    }

    [HttpPost("clear_logs")]
    public async Task<ActionResult<BaseResult<int>>> ClearLogs([FromBody] ClearLogsRequest request)
    {
        try
        {
            int deletedCount;

            if (request.ClearAll)
            {
                deletedCount = await logManagementService.ClearAllLogsAsync();
                return Success(deletedCount, $"成功清空所有日志，共删除 {deletedCount} 条记录");
            }
            else if (request.BeforeDate.HasValue)
            {
                deletedCount = await logManagementService.ClearLogsByDateAsync(request.BeforeDate.Value);
                return Success(deletedCount, $"成功清空 {request.BeforeDate.Value:yyyy-MM-dd} 之前的日志，共删除 {deletedCount} 条记录");
            }
            else
            {
                return Error<int>("请指定清空条件：要么清空全部，要么指定日期");
            }
        }
        catch (Exception ex)
        {
            return Error<int>($"清空日志失败: {ex.Message}", 500);
        }
    }

    [HttpGet("get_statistics")]
    public async Task<ActionResult<BaseResult<LogStatistics>>> GetLogStatistics()
    {
        try
        {
            var statistics = await logManagementService.GetLogStatisticsAsync();
            return Success(statistics, "日志统计获取成功");
        }
        catch (Exception ex)
        {
            return Error<LogStatistics>($"获取日志统计失败: {ex.Message}", 500);
        }
    }
}
