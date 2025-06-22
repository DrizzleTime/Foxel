using Foxel.Models;
using Foxel.Models.DataBase;
using Foxel.Models.Response.Tag;
using Microsoft.EntityFrameworkCore;

namespace Foxel.Services.Media;

public class TagService(IDbContextFactory<MyDbContext> contextFactory, ILogger<TagService> logger) : ITagService
{
    public async Task<PaginatedResult<TagResponse>> GetFilteredTagsAsync(
        int page = 1,
        int pageSize = 20,
        string? searchQuery = null,
        string? sortBy = "pictureCount",
        string? sortDirection = "desc",
        int? minPictureCount = null)
    {
        try
        {
            if (page < 1) page = 1;
            if (pageSize < 1 || pageSize > 100) pageSize = 20;

            await using var dbContext = await contextFactory.CreateDbContextAsync();

            // 构建基础查询，确保加载图片关联
            IQueryable<Tag> query = dbContext.Tags.Include(t => t.Pictures);

            // 应用搜索条件
            if (!string.IsNullOrWhiteSpace(searchQuery))
            {
                var searchTerm = searchQuery.ToLower();
                query = query.Where(t =>
                    t.Name.ToLower().Contains(searchTerm) ||
                    (t.Description != null && t.Description.ToLower().Contains(searchTerm)));
            }

            // 应用最小图片数量过滤（安全处理Pictures集合）
            if (minPictureCount.HasValue && minPictureCount.Value > 0)
            {
                query = query.Where(t => t.Pictures != null && t.Pictures.Count >= minPictureCount.Value);
            }

            // 获取总记录数（先计算总数再排序和分页）
            var totalCount = await query.CountAsync();

            // 没有结果时返回空列表
            if (totalCount == 0)
            {
                return new PaginatedResult<TagResponse>
                {
                    Data = new List<TagResponse>(),
                    TotalCount = 0,
                    Page = page,
                    PageSize = pageSize
                };
            }

            // 应用排序
            query = ApplySorting(query, sortBy, sortDirection);

            // 应用分页
            var tags = await query
                .Skip((page - 1) * pageSize)
                .Take(pageSize)
                .ToListAsync();

            // 转换为响应格式，确保包含图片数量
            var tagResponses = new List<TagResponse>();

            foreach (var tag in tags)
            {
                tagResponses.Add(new TagResponse
                {
                    Id = tag.Id,
                    Name = tag.Name,
                    Description = tag.Description,
                    CreatedAt = tag.CreatedAt,
                    PictureCount = tag.Pictures?.Count ?? 0 // 确保包含图片数量
                });
            }

            return new PaginatedResult<TagResponse>
            {
                Data = tagResponses,
                TotalCount = totalCount,
                Page = page,
                PageSize = pageSize
            };
        }
        catch (Exception ex)
        {
            // 记录详细错误信息
            logger.LogError(ex, "GetFilteredTagsAsync error");

            throw;
        }
    }

    // 添加排序方法
    private static IQueryable<Tag> ApplySorting(
        IQueryable<Tag> query,
        string? sortBy,
        string? sortDirection)
    {
        var isAscending = string.Equals(sortDirection, "asc", StringComparison.OrdinalIgnoreCase);

        return sortBy?.ToLower() switch
        {
            "name" => isAscending
                ? query.OrderBy(t => t.Name)
                : query.OrderByDescending(t => t.Name),

            "createdat" => isAscending
                ? query.OrderBy(t => t.CreatedAt)
                : query.OrderByDescending(t => t.CreatedAt),

            "picturecount" => isAscending
                ? query.OrderBy(t => t.Pictures.Count)
                : query.OrderByDescending(t => t.Pictures.Count),

            _ => query.OrderByDescending(t => t.Pictures.Count) // 默认按图片数量降序排列
        };
    }

    public async Task<TagResponse> GetTagByIdAsync(int id)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var tag = await dbContext.Tags
            .Include(t => t.Pictures)
            .FirstOrDefaultAsync(t => t.Id == id);

        if (tag == null)
            throw new KeyNotFoundException($"找不到ID为{id}的标签");

        return new TagResponse
        {
            Id = tag.Id,
            Name = tag.Name,
            Description = tag.Description,
            CreatedAt = tag.CreatedAt,
            PictureCount = tag.Pictures?.Count ?? 0
        };
    }

    public async Task<TagResponse> CreateTagAsync(string name, string? description = null)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("标签名称不能为空");

        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 检查是否已存在同名标签
        var existingTag = await dbContext.Tags.FirstOrDefaultAsync(t => t.Name.ToLower() == name.ToLower());
        if (existingTag != null)
            throw new InvalidOperationException("已存在相同名称的标签");

        var tag = new Tag
        {
            Name = name.Trim(),
            Description = description?.Trim(),
            CreatedAt = DateTime.UtcNow,
            Pictures = new List<Picture>() // 初始化为空集合而不是null
        };

        dbContext.Tags.Add(tag);
        await dbContext.SaveChangesAsync();

        return new TagResponse
        {
            Id = tag.Id,
            Name = tag.Name,
            Description = tag.Description,
            CreatedAt = tag.CreatedAt,
            PictureCount = 0
        };
    }

    public async Task<TagResponse> UpdateTagAsync(int id, string? name = null, string? description = null)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var tag = await dbContext.Tags.FindAsync(id);
        if (tag == null)
            throw new KeyNotFoundException($"找不到ID为{id}的标签");

        if (!string.IsNullOrWhiteSpace(name))
        {
            // 检查是否已存在同名标签（不包括当前标签）
            var existingTag =
                await dbContext.Tags.FirstOrDefaultAsync(t => t.Id != id && t.Name.ToLower() == name.ToLower());

            if (existingTag != null)
                throw new InvalidOperationException("已存在相同名称的标签");

            tag.Name = name.Trim();
        }

        if (description != null) // 允许设置为空字符串
        {
            tag.Description = description.Trim();
        }

        tag.UpdatedAt = DateTime.UtcNow;

        await dbContext.SaveChangesAsync();

        return new TagResponse
        {
            Id = tag.Id,
            Name = tag.Name,
            Description = tag.Description,
            CreatedAt = tag.CreatedAt,
            PictureCount = tag.Pictures?.Count ?? 0
        };
    }

    public async Task<bool> DeleteTagAsync(int id)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var tag = await dbContext.Tags.FindAsync(id);
        if (tag == null)
            throw new KeyNotFoundException($"找不到ID为{id}的标签");

        dbContext.Tags.Remove(tag);
        await dbContext.SaveChangesAsync();

        return true;
    }
}