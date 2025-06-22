using Foxel.Services.Configuration;

namespace Foxel.Services.VectorDb;

public class VectorDbInitializer : IHostedService
{
    private readonly IVectorDbService _vectorDbService;
    private readonly IConfigService _configService;
    private const string VectorDbTypeConfigKey = "VectorDb:Type";

    public VectorDbInitializer(IVectorDbService vectorDbService, IConfigService configService)
    {
        _vectorDbService = vectorDbService;
        _configService = configService;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var dbTypeStr = await _configService.GetValueAsync(VectorDbTypeConfigKey) ?? "InMemory";
        if (string.Equals(dbTypeStr, "InMemory", StringComparison.OrdinalIgnoreCase))
        {
            await _vectorDbService.BuildUserPictureVectorsAsync();
        }
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        return Task.CompletedTask;
    }
}
