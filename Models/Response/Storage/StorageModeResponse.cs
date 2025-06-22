using Foxel.Services.Storage;

// For StorageType enum

namespace Foxel.Models.Response.Storage;

public class StorageModeResponse
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public StorageType StorageType { get; set; }
    public string StorageTypeName => StorageType.ToString();
    public string? ConfigurationJson { get; set; } // Consider if this should be exposed or masked/summarized
    public bool IsEnabled { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
}
