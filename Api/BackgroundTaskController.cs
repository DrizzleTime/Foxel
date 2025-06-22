using Foxel.Models;
using Foxel.Services.Background;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api;

[Authorize]
[Route("api/background-tasks")]
public class BackgroundTaskController : BaseApiController
{
    private readonly IBackgroundTaskQueue _backgroundTaskQueue;

    public BackgroundTaskController(IBackgroundTaskQueue backgroundTaskQueue)
    {
        _backgroundTaskQueue = backgroundTaskQueue;
    }

    [HttpGet("user-tasks")]
    public async Task<ActionResult<BaseResult<List<TaskDetailsDto>>>> GetUserTasks()
    {
        try
        {
            var userId = GetCurrentUserId();
            if (userId == null)
                return Error<List<TaskDetailsDto>>("无法识别用户信息", 401);

            var tasks = await _backgroundTaskQueue.GetUserTasksStatusAsync(userId.Value);
            return Success(tasks, "成功获取任务列表");
        }
        catch (Exception ex)
        {
            return Error<List<TaskDetailsDto>>($"获取任务状态失败: {ex.Message}", 500);
        }
    }
}
