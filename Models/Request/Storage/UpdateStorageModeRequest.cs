using System.ComponentModel.DataAnnotations;
using Foxel.Services.Storage;

// For StorageType enum

namespace Foxel.Models.Request.Storage;

public class UpdateStorageModeRequest
{
    [Required]
    public int Id { get; set; }

    [Required]
    [StringLength(100)]
    public string Name { get; set; } = string.Empty;

    [Required]
    public StorageType StorageType { get; set; }

    public string? ConfigurationJson { get; set; }

    public bool IsEnabled { get; set; }
}
