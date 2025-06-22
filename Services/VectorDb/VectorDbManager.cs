using Foxel.Models.Vector;
using Foxel.Services.Configuration;
using Microsoft.EntityFrameworkCore;

namespace Foxel.Services.VectorDb;

public class VectorDbManager(IServiceProvider serviceProvider, IConfigService configService)
    : IVectorDbService
{
    private IVectorDbService? _currentService;
    private readonly Lock _lock = new();
    private const string VectorDbTypeConfigKey = "VectorDb:Type";

    private IVectorDbService GetCurrentService()
    {
        if (_currentService == null)
        {
            lock (_lock)
            {
                if (_currentService == null)
                {
                    var dbTypeStr = configService[VectorDbTypeConfigKey] ?? "InMemory";
                    if (Enum.TryParse<VectorDbType>(dbTypeStr, true, out var dbType))
                    {
                        _currentService = CreateVectorDbService(dbType);
                    }
                    else
                    {
                        _currentService = CreateVectorDbService(VectorDbType.InMemory);
                    }
                }
            }
        }

        return _currentService;
    }

    public async Task SwitchVectorDbAsync(VectorDbType type)
    {
        IVectorDbService oldService = null;

        lock (_lock)
        {
            var currentType = GetCurrentVectorDbType();
            if (currentType == type && _currentService != null)
            {
                return;
            }

            oldService = _currentService;
            _currentService = CreateVectorDbService(type);
        }

        await configService.SetConfigAsync(VectorDbTypeConfigKey, type.ToString(), "向量数据库类型");
        if (type == VectorDbType.InMemory)
        {
            await BuildUserPictureVectorsAsync();
        }
    }

    public VectorDbType GetCurrentVectorDbType()
    {
        var currentService = GetCurrentService();
        if (currentService is InMemoryVectorDbService)
            return VectorDbType.InMemory;
        if (currentService is QdrantVectorDbService)
            return VectorDbType.Qdrant;
        return VectorDbType.InMemory;
    }

    private IVectorDbService CreateVectorDbService(VectorDbType type)
    {
        var dbContextFactory = serviceProvider.GetRequiredService<IDbContextFactory<MyDbContext>>();

        return type switch
        {
            VectorDbType.InMemory => new InMemoryVectorDbService(dbContextFactory),
            VectorDbType.Qdrant => new QdrantVectorDbService(dbContextFactory, configService),
            _ => new InMemoryVectorDbService(dbContextFactory)
        };
    }

    public Task BuildUserPictureVectorsAsync() => GetCurrentService().BuildUserPictureVectorsAsync();

    public Task<List<PictureVector>> SearchAsync(ReadOnlyMemory<float> query, int? userId, int topK = 10)
        => GetCurrentService().SearchAsync(query, userId, topK);

    public Task AddPictureToUserCollectionAsync(int userId, PictureVector pictureVector)
        => GetCurrentService().AddPictureToUserCollectionAsync(userId, pictureVector);

    public Task RemovePictureFromUserCollectionAsync(int userId, int pictureId)
        => GetCurrentService().RemovePictureFromUserCollectionAsync(userId, pictureId);

    public Task ClearVectorsAsync() => GetCurrentService().ClearVectorsAsync();
}