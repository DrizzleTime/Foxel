using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Foxel.Services.Storage;

namespace Foxel.Models.DataBase;

public class StorageMode : BaseModel
{
    [Required]
    [StringLength(100)]
    public string Name { get; set; } = string.Empty;
    public bool IsEnabled { get; set; } = true;

    public StorageType StorageType { get; set; } = StorageType.Local;
    [Column(TypeName = "jsonb")] public string? ConfigurationJson { get; set; }
}
