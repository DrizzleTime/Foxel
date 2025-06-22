using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using System.Text.Json;

namespace Foxel.Models.DataBase;

public class Picture : BaseModel
{
    [StringLength(255)] public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Path to the high-definition (possibly format-converted) image.
    /// </summary>
    [StringLength(1024)] public string Path { get; set; } = string.Empty;

    /// <summary>
    /// Path to the original, untouched uploaded file.
    /// </summary>
    [StringLength(1024)] public string OriginalPath { get; set; } = string.Empty;

    [StringLength(1024)] public string? ThumbnailPath { get; set; } = string.Empty;

    [StringLength(2000)] public string Description { get; set; } = string.Empty;
    public float[]? Embedding { get; set; }

    public DateTime? TakenAt { get; set; }

    [Column(TypeName = "jsonb")] public string? ExifInfoJson { get; set; }

    [NotMapped]
    public ExifInfo? ExifInfo
    {
        get => ExifInfoJson != null ? JsonSerializer.Deserialize<ExifInfo>(ExifInfoJson) : null;
        set => ExifInfoJson = value != null ? JsonSerializer.Serialize(value) : null;
    }

    public int StorageModeId { get; set; }
    [ForeignKey("StorageModeId")]
    public StorageMode? StorageMode { get; set; } = null!;

    public ICollection<Tag>? Tags { get; set; }
    public int? UserId { get; set; }

    public User? User { get; set; }

    public int? AlbumId { get; set; }
    public Album? Album { get; set; }

    public ICollection<Favorite>? Favorites { get; set; }
    
    public ICollection<Face>? Faces { get; set; }

    public bool ContentWarning { get; set; } = false;
    public PermissionType Permission { get; set; } = PermissionType.Public;
}

public enum PermissionType
{
    Public = 0,
    Friends = 1,
    Private = 2
}
