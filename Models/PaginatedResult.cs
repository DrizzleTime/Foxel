namespace Foxel.Models;

public record PaginatedResult<T> : BaseResult<List<T>>
{
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 10;
    public int TotalCount { get; init; }
}