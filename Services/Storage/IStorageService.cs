namespace Foxel.Services.Storage;

/// <summary>
/// 统一的存储服务接口
/// </summary>
public interface IStorageService
{
    /// <summary>
    /// 在指定存储模式上执行操作
    /// </summary>
    /// <typeparam name="TResult">操作结果类型</typeparam>
    /// <param name="storageModeId">存储模式的ID</param>
    /// <param name="operation">要执行的操作</param>
    /// <returns>操作结果</returns>
    Task<TResult> ExecuteAsync<TResult>(int storageModeId, Func<IStorageProvider, Task<TResult>> operation);
    
    /// <summary>
    /// 在指定存储模式上执行无返回值的操作
    /// </summary>
    /// <param name="storageModeId">存储模式的ID</param>
    /// <param name="operation">要执行的操作</param>
    Task ExecuteAsync(int storageModeId, Func<IStorageProvider, Task> operation);
}
