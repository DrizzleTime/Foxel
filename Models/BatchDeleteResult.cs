namespace Foxel.Models;

public class BatchDeleteResult
{
    public int SuccessCount { get; set; }
    public int FailedCount { get; set; }
    public List<int> FailedIds { get; set; } = new();
}