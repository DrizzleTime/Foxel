using Foxel.Models.Vector;

namespace Foxel.Services.VectorDb;

public interface IVectorDbService
{
    Task BuildUserPictureVectorsAsync();
    Task<List<PictureVector>> SearchAsync(ReadOnlyMemory<float> query, int? userId, int topK = 10);
    Task AddPictureToUserCollectionAsync(int userId, PictureVector pictureVector);
    Task RemovePictureFromUserCollectionAsync(int userId, int pictureId);
    Task ClearVectorsAsync();
}

public enum VectorDbType
{
    InMemory,
    Qdrant
}