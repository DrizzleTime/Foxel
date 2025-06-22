using Foxel.Models.DataBase;
using Foxel.Services.Storage;
using Foxel.Utils;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;

namespace Foxel.Services.Background.Processors
{
    public class PictureProcessingPayload
    {
        public int PictureId { get; set; }
        public string OriginalFilePath { get; set; } = string.Empty;
        public int? UserIdForPicture { get; set; }
    }

    public class PictureTaskProcessor(
        IDbContextFactory<MyDbContext> contextFactory,
        IServiceProvider serviceProvider,
        ILogger<PictureTaskProcessor> logger)
        : ITaskProcessor
    {
        public async Task ProcessAsync(BackgroundTask backgroundTask)
        {
            if (backgroundTask.Payload == null)
            {
                await UpdateTaskStatusInDb(backgroundTask.Id, TaskExecutionStatus.Failed, 0, "任务 Payload 为空。");
                logger.LogError("任务 Payload 为空: TaskId={TaskId}", backgroundTask.Id);
                return;
            }

            PictureProcessingPayload? payload;
            try
            {
                payload = JsonSerializer.Deserialize<PictureProcessingPayload>(backgroundTask.Payload);
            }
            catch (JsonException ex)
            {
                logger.LogError(ex, "无法解析图片处理任务的 Payload: TaskId={TaskId}", backgroundTask.Id);
                await UpdateTaskStatusInDb(backgroundTask.Id, TaskExecutionStatus.Failed, 0, "Payload 解析失败。");
                return;
            }

            if (payload == null || payload.PictureId == 0)
            {
                logger.LogError("图片处理任务的 Payload 无效或缺少 PictureId: TaskId={TaskId}", backgroundTask.Id);
                await UpdateTaskStatusInDb(backgroundTask.Id, TaskExecutionStatus.Failed, 0,
                    "Payload 无效或缺少 PictureId。");
                return;
            }

            var pictureId = payload.PictureId;
            var storageKeyForOriginalFile = payload.OriginalFilePath;
            string localFilePath = "";
            bool isTempFile = false;

            await using var dbContext = await contextFactory.CreateDbContextAsync();
            var currentBackgroundTaskState = await dbContext.BackgroundTasks.FindAsync(backgroundTask.Id);
            if (currentBackgroundTaskState == null)
            {
                logger.LogError("在 PictureTaskProcessor 中找不到后台任务: TaskId={TaskId}", backgroundTask.Id);
                return;
            }

            // Include StorageMode to access its StorageType
            var picture = await dbContext.Pictures
                .Include(p => p.User)
                .Include(p => p.StorageMode)
                .FirstOrDefaultAsync(p => p.Id == pictureId);

            try
            {
                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Processing, 10,
                    currentBackgroundTaskState: currentBackgroundTaskState);

                if (picture == null)
                {
                    throw new Exception($"找不到ID为{pictureId}的图片。");
                }

                if (picture.StorageMode == null || picture.StorageModeId < 0)
                {
                    throw new Exception($"图片ID {pictureId} 缺少有效的 StorageMode 配置。");
                }

                using var scope = serviceProvider.CreateScope();
                var storageService = scope.ServiceProvider.GetRequiredService<IStorageService>();

                if (picture.StorageMode.StorageType == StorageType.Local)
                {
                    logger.LogInformation(
                        "Picture {PictureId} is Local. Attempting to download via StorageService for consistency.",
                        pictureId);
                }

                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Processing, 25,
                    currentBackgroundTaskState: currentBackgroundTaskState);
                localFilePath = await storageService.ExecuteAsync(picture.StorageModeId,
                    provider => provider.DownloadFileAsync(storageKeyForOriginalFile)); // Use storageKeyForOriginalFile
                isTempFile = true;
                if (string.IsNullOrEmpty(localFilePath) || !File.Exists(localFilePath))
                {
                    throw new Exception($"找不到图片文件: {localFilePath} (源存储路径: {storageKeyForOriginalFile})");
                }

                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Processing, 50,
                    currentBackgroundTaskState: currentBackgroundTaskState);
                if (string.IsNullOrEmpty(picture.ThumbnailPath))
                {
                    var tempThumbContainer = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
                    Directory.CreateDirectory(tempThumbContainer);
                    string baseNameFromOriginalStorageKey = Path.GetFileNameWithoutExtension(picture.OriginalPath);
                    var thumbnailDiskPath = Path.Combine(tempThumbContainer,
                        $"{baseNameFromOriginalStorageKey}-thumbnail-temp.webp");
                    await ImageHelper.CreateThumbnailAsync(localFilePath, thumbnailDiskPath, 500);
                    await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Processing, 65,
                        currentBackgroundTaskState: currentBackgroundTaskState);
                    await using var thumbnailFileStream =
                        new FileStream(thumbnailDiskPath, FileMode.Open, FileAccess.Read);
                    var thumbnailStorageFileName = $"{baseNameFromOriginalStorageKey}-thumbnail.webp";
                    string storedThumbnailPath = await storageService.ExecuteAsync(
                        picture.StorageModeId,
                        provider => provider.SaveAsync(thumbnailFileStream, thumbnailStorageFileName, "image/webp"));
                    picture.ThumbnailPath = storedThumbnailPath;
                    if (Directory.Exists(tempThumbContainer)) Directory.Delete(tempThumbContainer, true);
                }

                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Processing, 80,
                    currentBackgroundTaskState: currentBackgroundTaskState);
                var exifInfo = await ImageHelper.ExtractExifInfoAsync(localFilePath);
                picture.ExifInfo = exifInfo;
                picture.TakenAt = ImageHelper.ParseExifDateTime(exifInfo.DateTimeOriginal);
                await dbContext.SaveChangesAsync();
                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Completed, 100,
                    completedAt: DateTime.UtcNow, currentBackgroundTaskState: currentBackgroundTaskState);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "图片元数据处理任务失败: TaskId={TaskId}, PictureId={PictureId}",
                    currentBackgroundTaskState.Id, pictureId);
                await UpdateTaskStatusInDb(currentBackgroundTaskState.Id, TaskExecutionStatus.Failed,
                    currentBackgroundTaskState.Progress, ex.Message,
                    currentBackgroundTaskState: currentBackgroundTaskState);
            }
            finally
            {
                if (isTempFile && File.Exists(localFilePath))
                {
                    try
                    {
                        File.Delete(localFilePath);
                    }
                    catch (Exception ex)
                    {
                        logger.LogWarning(ex, "删除临时主图片文件失败: {FilePath}", localFilePath);
                    }
                }
            }
        }

        private async Task UpdateTaskStatusInDb(Guid taskId, TaskExecutionStatus status, int progress,
            string? error = null, DateTime? startedAt = null, DateTime? completedAt = null,
            BackgroundTask? currentBackgroundTaskState = null)
        {
            await using var dbContext = await contextFactory.CreateDbContextAsync();
            var taskToUpdate = currentBackgroundTaskState ?? await dbContext.BackgroundTasks.FindAsync(taskId);

            if (taskToUpdate != null)
            {
                if (currentBackgroundTaskState != null &&
                    dbContext.Entry(currentBackgroundTaskState).State == EntityState.Detached)
                {
                    dbContext.BackgroundTasks.Attach(currentBackgroundTaskState);
                }

                taskToUpdate.Status = status;
                taskToUpdate.Progress = progress;
                taskToUpdate.ErrorMessage = string.IsNullOrEmpty(error) ? taskToUpdate.ErrorMessage : error;
                if (startedAt.HasValue) taskToUpdate.StartedAt = startedAt;
                if (completedAt.HasValue) taskToUpdate.CompletedAt = completedAt;

                if ((status == TaskExecutionStatus.Completed || status == TaskExecutionStatus.Failed) &&
                    !taskToUpdate.StartedAt.HasValue)
                {
                    taskToUpdate.StartedAt = taskToUpdate.CreatedAt;
                }

                if (status == TaskExecutionStatus.Completed || status == TaskExecutionStatus.Failed)
                {
                    taskToUpdate.CompletedAt ??= DateTime.UtcNow;
                }

                await dbContext.SaveChangesAsync();
                logger.LogInformation("任务状态更新 (Processor): TaskId={TaskId}, Status={Status}, Progress={Progress}%",
                    taskId, status, progress);
            }
            else
            {
                logger.LogWarning("尝试在 Processor 中更新不存在的任务状态: TaskId={TaskId}", taskId);
            }
        }
    }
}