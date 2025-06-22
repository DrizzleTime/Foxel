namespace Foxel.Services.Storage;

public enum StorageType
{
    Local = 0,
    Telegram = 1,
    S3 = 2,
    Cos = 3,
    WebDAV = 4,
}


/// <summary>
/// 标记存储提供者类的特性
/// </summary>
[AttributeUsage(AttributeTargets.Class)]
public class StorageProviderAttribute : Attribute
{
    /// <summary>
    /// 存储类型
    /// </summary>
    public StorageType StorageType { get; }

    /// <summary>
    /// 构造函数
    /// </summary>
    /// <param name="storageType">存储类型</param>
    public StorageProviderAttribute(StorageType storageType)
    {
        StorageType = storageType;
    }
}
