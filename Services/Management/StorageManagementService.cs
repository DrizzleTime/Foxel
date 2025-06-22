using Foxel.Models;
using Foxel.Models.DataBase;
using Foxel.Models.Request.Storage;
using Foxel.Models.Response.Storage;
using Foxel.Services.Storage.Providers; // Required for config types like LocalStorageConfig, etc.
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using System.Text.Json;
using Foxel.Services.Configuration;
using Foxel.Services.Storage; // Added for IConfigService

namespace Foxel.Services.Management;

public class StorageManagementService : IStorageManagementService
{
    private readonly IDbContextFactory<MyDbContext> _contextFactory;
    private readonly ILogger<StorageManagementService> _logger;
    private readonly IConfigService _configService; // Added IConfigService
    private const string DefaultStorageModeIdKey = "Storage:DefaultStorageModeId"; // Define key for config

    public StorageManagementService(
        IDbContextFactory<MyDbContext> contextFactory, 
        ILogger<StorageManagementService> logger,
        IConfigService configService) // Added IConfigService to constructor
    {
        _contextFactory = contextFactory;
        _logger = logger;
        _configService = configService; // Initialize IConfigService
    }

    public async Task<PaginatedResult<StorageModeResponse>> GetStorageModesAsync(int page = 1, int pageSize = 10, string? searchQuery = null, StorageType? storageType = null, bool? isEnabled = null)
    {
        if (page < 1) page = 1;
        if (pageSize < 1) pageSize = 10;

        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var query = dbContext.StorageModes.AsQueryable();

        if (!string.IsNullOrWhiteSpace(searchQuery))
        {
            query = query.Where(sm => sm.Name.Contains(searchQuery));
        }
        if (storageType.HasValue)
        {
            query = query.Where(sm => sm.StorageType == storageType.Value);
        }
        if (isEnabled.HasValue)
        {
            query = query.Where(sm => sm.IsEnabled == isEnabled.Value);
        }

        query = query.OrderByDescending(sm => sm.CreatedAt);

        var totalCount = await query.CountAsync();
        var storageModes = await query
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync();

        var responseItems = storageModes.Select(sm => new StorageModeResponse
        {
            Id = sm.Id,
            Name = sm.Name,
            StorageType = sm.StorageType,
            ConfigurationJson = sm.ConfigurationJson, // Consider masking sensitive info if necessary
            IsEnabled = sm.IsEnabled,
            CreatedAt = sm.CreatedAt,
            UpdatedAt = sm.UpdatedAt
        }).ToList();

        return new PaginatedResult<StorageModeResponse>
        {
            Data = responseItems,
            Page = page,
            PageSize = pageSize,
            TotalCount = totalCount
        };
    }

    public async Task<StorageModeResponse> GetStorageModeByIdAsync(int id)
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var sm = await dbContext.StorageModes.FindAsync(id);
        if (sm == null)
            throw new KeyNotFoundException($"StorageMode with ID {id} not found.");

        return new StorageModeResponse
        {
            Id = sm.Id,
            Name = sm.Name,
            StorageType = sm.StorageType,
            ConfigurationJson = sm.ConfigurationJson,
            IsEnabled = sm.IsEnabled,
            CreatedAt = sm.CreatedAt,
            UpdatedAt = sm.UpdatedAt
        };
    }

    public async Task<StorageModeResponse> CreateStorageModeAsync(CreateStorageModeRequest request)
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();

        ValidateConfiguration(request.StorageType, request.ConfigurationJson, request.Name);

        var storageMode = new Models.DataBase.StorageMode
        {
            Name = request.Name,
            StorageType = request.StorageType,
            ConfigurationJson = request.ConfigurationJson,
            IsEnabled = request.IsEnabled,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow
        };

        dbContext.StorageModes.Add(storageMode);
        await dbContext.SaveChangesAsync();

        return await GetStorageModeByIdAsync(storageMode.Id); // Reuse to get full response model
    }

    public async Task<StorageModeResponse> UpdateStorageModeAsync(UpdateStorageModeRequest request)
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var storageMode = await dbContext.StorageModes.FindAsync(request.Id);

        if (storageMode == null)
            throw new KeyNotFoundException($"StorageMode with ID {request.Id} not found.");

        ValidateConfiguration(request.StorageType, request.ConfigurationJson, request.Name);

        storageMode.Name = request.Name;
        storageMode.StorageType = request.StorageType;
        storageMode.ConfigurationJson = request.ConfigurationJson;
        storageMode.IsEnabled = request.IsEnabled;
        storageMode.UpdatedAt = DateTime.UtcNow;

        await dbContext.SaveChangesAsync();
        return await GetStorageModeByIdAsync(storageMode.Id);
    }

    public async Task<bool> DeleteStorageModeAsync(int id)
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var storageMode = await dbContext.StorageModes.FindAsync(id);
        if (storageMode == null)
            throw new KeyNotFoundException($"StorageMode with ID {id} not found.");
        
        // Check if any pictures are using this storage mode
        bool isInUse = await dbContext.Pictures.AnyAsync(p => p.StorageModeId == id);
        if (isInUse)
        {
            _logger.LogWarning("Attempted to delete StorageMode ID {StorageModeId} which is currently in use by one or more pictures.", id);
            throw new InvalidOperationException($"StorageMode '{storageMode.Name}' (ID: {id}) cannot be deleted because it is currently in use by one or more pictures.");
        }

        dbContext.StorageModes.Remove(storageMode);
        await dbContext.SaveChangesAsync();
        return true;
    }

    public async Task<BatchDeleteResult> BatchDeleteStorageModesAsync(List<int> ids)
    {
        var result = new BatchDeleteResult();
        await using var dbContext = await _contextFactory.CreateDbContextAsync();

        foreach (var id in ids)
        {
            var storageMode = await dbContext.StorageModes.FindAsync(id);
            if (storageMode == null)
            {
                result.FailedCount++;
                result.FailedIds.Add(id);
                _logger.LogWarning("Batch delete: StorageMode with ID {StorageModeId} not found.", id);
                continue;
            }

            bool isInUse = await dbContext.Pictures.AnyAsync(p => p.StorageModeId == id);
            if (isInUse)
            {
                result.FailedCount++;
                result.FailedIds.Add(id);
                _logger.LogWarning("Batch delete: StorageMode ID {StorageModeId} ('{StorageModeName}') is in use and cannot be deleted.", id, storageMode.Name);
                continue;
            }
            
            try
            {
                dbContext.StorageModes.Remove(storageMode);
                result.SuccessCount++;
            }
            catch (Exception ex)
            {
                result.FailedCount++;
                result.FailedIds.Add(id);
                _logger.LogError(ex, "Batch delete: Error deleting StorageMode ID {StorageModeId}.", id);
            }
        }
        if (result.SuccessCount > 0)
        {
            await dbContext.SaveChangesAsync();
        }
        return result;
    }
    
    public Task<IEnumerable<StorageTypeResponse>> GetStorageTypesAsync()
    {
        var types = Enum.GetValues(typeof(StorageType))
            .Cast<StorageType>()
            .Select(e => new StorageTypeResponse { Value = (int)e, Name = e.ToString() })
            .ToList();
        return Task.FromResult<IEnumerable<StorageTypeResponse>>(types);
    }

    public async Task<int?> GetDefaultStorageModeIdAsync()
    {
        var idString = await _configService.GetValueAsync(DefaultStorageModeIdKey);
        if (int.TryParse(idString, out var id))
        {
            // Optionally, verify if this ID still exists and is enabled in StorageModes table
            await using var dbContext = await _contextFactory.CreateDbContextAsync();
            var storageModeExists = await dbContext.StorageModes.AnyAsync(sm => sm.Id == id && sm.IsEnabled);
            if (storageModeExists)
            {
                return id;
            }
            _logger.LogWarning("Default storage mode ID {DefaultStorageModeId} from config does not exist or is not enabled.", id);
            // If it doesn't exist or isn't enabled, perhaps clear the setting or return null
            // For now, returning null as it's not a valid/usable default
            await _configService.DeleteConfigAsync(DefaultStorageModeIdKey); // Clean up invalid setting
            return null;
        }
        return null;
    }

    public async Task<bool> SetDefaultStorageModeAsync(int storageModeId)
    {
        await using var dbContext = await _contextFactory.CreateDbContextAsync();
        var storageMode = await dbContext.StorageModes.FindAsync(storageModeId);

        if (storageMode == null)
        {
            _logger.LogWarning("Attempted to set default storage mode to a non-existent ID: {StorageModeId}", storageModeId);
            throw new KeyNotFoundException($"StorageMode with ID {storageModeId} not found.");
        }

        if (!storageMode.IsEnabled)
        {
            _logger.LogWarning("Attempted to set default storage mode to a disabled StorageMode ID: {StorageModeId}, Name: {StorageModeName}", storageModeId, storageMode.Name);
            throw new InvalidOperationException($"StorageMode '{storageMode.Name}' (ID: {storageModeId}) is disabled and cannot be set as default.");
        }
        
        // Validate configuration before setting as default
        try
        {
            ValidateConfiguration(storageMode.StorageType, storageMode.ConfigurationJson, storageMode.Name);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Validation failed for StorageMode ID {StorageModeId} ('{StorageModeName}') when trying to set as default. Configuration: {ConfigurationJson}", storageModeId, storageMode.Name, storageMode.ConfigurationJson);
            throw new InvalidOperationException($"StorageMode '{storageMode.Name}' (ID: {storageModeId}) has an invalid configuration and cannot be set as default. Error: {ex.Message}", ex);
        }


        await _configService.SetConfigAsync(DefaultStorageModeIdKey, storageModeId.ToString(), "The ID of the default storage mode to be used by the application.");
        _logger.LogInformation("Default storage mode set to ID: {StorageModeId}, Name: {StorageModeName}", storageModeId, storageMode.Name);
        return true;
    }

    private void ValidateConfiguration(StorageType storageType, string? jsonConfig, string storageModeName)
    {
        if (string.IsNullOrWhiteSpace(jsonConfig))
        {
            // Configuration can be optional for some types or scenarios,
            // but if a type inherently requires config, this check might need adjustment.
            // For now, we assume if jsonConfig is null/empty, it's intentional.
            // The actual provider instantiation will fail if config is required but missing.
            // This validation step is more about format if config IS provided.
            return;
        }

        try
        {
            object? deserializedConfig = storageType switch
            {
                StorageType.Local => JsonSerializer.Deserialize<LocalStorageConfig>(jsonConfig),
                StorageType.Telegram => JsonSerializer.Deserialize<TelegramStorageConfig>(jsonConfig),
                StorageType.S3 => JsonSerializer.Deserialize<S3StorageConfig>(jsonConfig),
                StorageType.Cos => JsonSerializer.Deserialize<CosStorageConfig>(jsonConfig),
                StorageType.WebDAV => JsonSerializer.Deserialize<WebDavStorageConfig>(jsonConfig),
                _ => throw new NotSupportedException($"StorageType {storageType} configuration validation is not supported.")
            };

            if (deserializedConfig == null)
            {
                throw new JsonException($"Unable to deserialize configuration for {storageType}. JSON: {jsonConfig}");
            }
            // Further property-level validation can be added here if needed (e.g., checking required fields within the config object)
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Invalid JSON configuration for StorageMode '{StorageModeName}' (Type: {StorageType}). JSON: {JsonConfig}", storageModeName, storageType, jsonConfig);
            throw new ArgumentException($"Configuration for StorageMode '{storageModeName}' (Type: {storageType}) is invalid: {ex.Message}", nameof(jsonConfig), ex);
        }
        catch (NotSupportedException ex)
        {
             _logger.LogError(ex, "Validation not supported for StorageType '{StorageType}' in StorageMode '{StorageModeName}'.", storageType, storageModeName);
            throw new ArgumentException(ex.Message, nameof(storageType), ex);
        }
    }
}
