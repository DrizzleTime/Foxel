using Foxel.Models.Vector;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;

namespace Foxel.Services.VectorDb;

public class InMemoryVectorDbService : IVectorDbService
{
    private readonly VectorStore _vectorStore;
    private readonly IDbContextFactory<MyDbContext> _contextFactory;

    public InMemoryVectorDbService(IDbContextFactory<MyDbContext> contextFactory)
    {
        _vectorStore = new InMemoryVectorStore();
        _contextFactory = contextFactory;
    }

    public async Task BuildUserPictureVectorsAsync()
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var userPictures = dbContext.Pictures
            .Where(p => p.UserId != null && p.Embedding != null)
            .Select(p => new { p.Id, p.Name, p.Embedding, p.UserId })
            .GroupBy(p => p.UserId!.Value)
            .ToList();

        foreach (var group in userPictures)
        {
            int userId = group.Key;
            var collectionName = $"picture_{userId}";
            var collection = _vectorStore.GetCollection<ulong, PictureVector>(collectionName);
            await collection.EnsureCollectionExistsAsync();

            var picVectors = group.Select(p => new PictureVector
            {
                Id = (ulong)p.Id,
                Name = p.Name,
                Embedding = p.Embedding
            }).ToList();

            foreach (var picVector in picVectors)
            {
                await collection.UpsertAsync(picVector);
            }
        }
    }

    public async Task<List<PictureVector>> SearchAsync(ReadOnlyMemory<float> query, int? userId, int topK = 10)
    {
        var collectionName = $"picture_{userId}";
        var collection = _vectorStore.GetCollection<ulong, PictureVector>(collectionName);
        var results = collection.SearchAsync(query, topK);
        var res = new List<PictureVector>();
        await foreach (var record in results)
        {
            res.Add(record.Record);
        }

        return res;
    }

    public async Task AddPictureToUserCollectionAsync(int userId, PictureVector pictureVector)
    {
        var collectionName = $"picture_{userId}";
        var collection = _vectorStore.GetCollection<ulong, PictureVector>(collectionName);
        await collection.EnsureCollectionExistsAsync();
        await collection.UpsertAsync(pictureVector);
    }

    public async Task RemovePictureFromUserCollectionAsync(int userId, int pictureId)
    {
        var collectionName = $"picture_{userId}";
        var collection = _vectorStore.GetCollection<ulong, PictureVector>(collectionName);
        await collection.EnsureCollectionExistsAsync();
        await collection.DeleteAsync((ulong)pictureId);
    }

    public async Task ClearVectorsAsync()
    {
        var collections = _vectorStore.ListCollectionNamesAsync();
        await foreach (var name in collections)
        {
            var collection = _vectorStore.GetCollection<ulong, PictureVector>(name);
            await collection.EnsureCollectionDeletedAsync();
        }
    }
}