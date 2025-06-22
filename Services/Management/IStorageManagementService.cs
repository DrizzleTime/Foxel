using Foxel.Models; // For PaginatedResult
using Foxel.Models.Request.Storage;
using Foxel.Models.Response.Storage;
using Foxel.Services.Storage;

// For StorageType

namespace Foxel.Services.Management;

public interface IStorageManagementService
{
    Task<PaginatedResult<StorageModeResponse>> GetStorageModesAsync(int page = 1, int pageSize = 10, string? searchQuery = null, StorageType? storageType = null, bool? isEnabled = null);
    Task<StorageModeResponse> GetStorageModeByIdAsync(int id);
    Task<StorageModeResponse> CreateStorageModeAsync(CreateStorageModeRequest request);
    Task<StorageModeResponse> UpdateStorageModeAsync(UpdateStorageModeRequest request);
    Task<bool> DeleteStorageModeAsync(int id);
    Task<BatchDeleteResult> BatchDeleteStorageModesAsync(List<int> ids);
    Task<IEnumerable<StorageTypeResponse>> GetStorageTypesAsync();
    Task<int?> GetDefaultStorageModeIdAsync();
    Task<bool> SetDefaultStorageModeAsync(int storageModeId);
}
