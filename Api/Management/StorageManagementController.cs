using Foxel.Models;
using Foxel.Models.Request.Storage;
using Foxel.Models.Response.Storage;
using Foxel.Services.Management;
using Foxel.Services.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Foxel.Api.Management;

[Authorize(Roles = "Administrator")]
[Route("api/management/storage")]
public class StorageManagementController(IStorageManagementService storageManagementService) : BaseApiController
{
    [AllowAnonymous]
    [HttpGet("get_available_modes")]
    public async Task<ActionResult<BaseResult<List<StorageModeResponse>>>> GetAvailableStorageModes()
    {
        try
        {
            var result = await storageManagementService.GetStorageModesAsync();
            var filteredModes = result.Data!
                .Where(mode => mode.IsEnabled)
                .Select(mode => new StorageModeResponse
                {
                    Id = mode.Id,
                    Name = mode.Name,
                    StorageType = mode.StorageType,
                    IsEnabled = mode.IsEnabled
                })
                .ToList();
            return Success(filteredModes, "Available storage modes retrieved successfully.");
        }
        catch (Exception ex)
        {
            return Error<List<StorageModeResponse>>($"Failed to get available storage modes: {ex.Message}", 500);
        }
    }

    [HttpGet("get_modes")]
    public async Task<ActionResult<PaginatedResult<StorageModeResponse>>> GetStorageModes(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 10,
        [FromQuery] string? searchQuery = null,
        [FromQuery] StorageType? storageType = null,
        [FromQuery] bool? isEnabled = null)
    {
        try
        {
            var result =
                await storageManagementService.GetStorageModesAsync(page, pageSize, searchQuery, storageType,
                    isEnabled);
            return PaginatedSuccess(result.Data, result.TotalCount, result.Page, result.PageSize);
        }
        catch (Exception ex)
        {
            return PaginatedError<StorageModeResponse>($"Failed to get storage modes: {ex.Message}", 500);
        }
    }

    [HttpGet("get_mode/{id}")]
    public async Task<ActionResult<BaseResult<StorageModeResponse>>> GetStorageModeById(int id)
    {
        try
        {
            var result = await storageManagementService.GetStorageModeByIdAsync(id);
            return Success(result, "Storage mode retrieved successfully.");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<StorageModeResponse>(ex.Message, 404);
        }
        catch (Exception ex)
        {
            return Error<StorageModeResponse>($"Failed to get storage mode: {ex.Message}", 500);
        }
    }

    [HttpPost("create_mode")]
    public async Task<ActionResult<BaseResult<StorageModeResponse>>> CreateStorageMode(
        [FromBody] CreateStorageModeRequest request)
    {
        try
        {
            var result = await storageManagementService.CreateStorageModeAsync(request);
            return Success(result, "Storage mode created successfully.");
        }
        catch (ArgumentException ex)
        {
            return Error<StorageModeResponse>(ex.Message, 400);
        }
        catch (Exception ex)
        {
            return Error<StorageModeResponse>($"Failed to create storage mode: {ex.Message}", 500);
        }
    }

    [HttpPost("update_mode")]
    public async Task<ActionResult<BaseResult<StorageModeResponse>>> UpdateStorageMode(
        [FromBody] UpdateStorageModeRequest request)
    {
        try
        {
            var result = await storageManagementService.UpdateStorageModeAsync(request);
            return Success(result, "Storage mode updated successfully.");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<StorageModeResponse>(ex.Message, 404);
        }
        catch (ArgumentException ex)
        {
            return Error<StorageModeResponse>(ex.Message, 400);
        }
        catch (Exception ex)
        {
            return Error<StorageModeResponse>($"Failed to update storage mode: {ex.Message}", 500);
        }
    }

    [HttpPost("delete_mode")]
    public async Task<ActionResult<BaseResult<bool>>> DeleteStorageMode([FromBody] int id)
    {
        try
        {
            var result = await storageManagementService.DeleteStorageModeAsync(id);
            return Success(result, "Storage mode deleted successfully.");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>(ex.Message, 404);
        }
        catch (InvalidOperationException ex) // Catch specific exception for "in use"
        {
            return Error<bool>(ex.Message, 400);
        }
        catch (Exception ex)
        {
            return Error<bool>($"Failed to delete storage mode: {ex.Message}", 500);
        }
    }

    [HttpPost("batch_delete_modes")]
    public async Task<ActionResult<BaseResult<BatchDeleteResult>>> BatchDeleteStorageModes([FromBody] List<int> ids)
    {
        try
        {
            if (ids == null || !ids.Any())
            {
                return Error<BatchDeleteResult>("No IDs provided for batch deletion.", 400);
            }

            var result = await storageManagementService.BatchDeleteStorageModesAsync(ids);
            return Success(result,
                $"Batch delete completed. Succeeded: {result.SuccessCount}, Failed: {result.FailedCount}.");
        }
        catch (Exception ex)
        {
            return Error<BatchDeleteResult>($"Batch delete failed: {ex.Message}", 500);
        }
    }

    [HttpGet("get_storage_types")]
    public async Task<ActionResult<BaseResult<IEnumerable<StorageTypeResponse>>>> GetStorageTypes()
    {
        try
        {
            var result = await storageManagementService.GetStorageTypesAsync();
            return Success(result, "Storage types retrieved successfully.");
        }
        catch (Exception ex)
        {
            return Error<IEnumerable<StorageTypeResponse>>($"Failed to get storage types: {ex.Message}", 500);
        }
    }

    [HttpGet("get_default_mode_id")]
    public async Task<ActionResult<BaseResult<int?>>> GetDefaultStorageModeId()
    {
        try
        {
            var result = await storageManagementService.GetDefaultStorageModeIdAsync();
            if (result.HasValue)
            {
                return Success<int?>(result.Value, "Default storage mode ID retrieved successfully.");
            }

            return Success<int?>(null, "No default storage mode is currently set or the configured one is invalid.");
        }
        catch (Exception ex)
        {
            return Error<int?>($"Failed to get default storage mode ID: {ex.Message}", 500);
        }
    }

    [HttpPost("set_default_mode/{id}")]
    public async Task<ActionResult<BaseResult<bool>>> SetDefaultStorageMode(int id)
    {
        try
        {
            var result = await storageManagementService.SetDefaultStorageModeAsync(id);
            return Success(result, $"Default storage mode set to ID {id} successfully.");
        }
        catch (KeyNotFoundException ex)
        {
            return Error<bool>(ex.Message, 404);
        }
        catch (InvalidOperationException ex)
        {
            return Error<bool>(ex.Message, 400);
        }
        catch (Exception ex)
        {
            return Error<bool>($"Failed to set default storage mode: {ex.Message}", 500);
        }
    }
}