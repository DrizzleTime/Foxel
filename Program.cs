using Foxel.Extensions;
using Foxel.Services.Initializer;
using Foxel.Services.VectorDb;
using Microsoft.AspNetCore.HttpOverrides;

var builder = WebApplication.CreateBuilder(args);
var environment = builder.Environment;
Console.WriteLine($"当前环境: {environment.EnvironmentName}");
builder.Logging.AddDatabaseLogging(config =>
{
    config.MinLevel = LogLevel.Information; 
    config.Enabled = true;
});
builder.Services.AddMemoryCache();
builder.Services.AddApplicationDbContext(builder.Configuration);
builder.Services.AddApplicationOpenApi();
builder.Services.AddControllers();
builder.Services.AddHttpClient();
builder.Services.AddCoreServices();
builder.Services.AddHttpContextAccessor();
builder.Services.AddApplicationAuthentication();
builder.Services.AddApplicationAuthorization();
builder.Services.AddApplicationCors();
builder.Services.AddVectorDbServices();
builder.Services.AddHostedService<VectorDbInitializer>();
builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    options.KnownNetworks.Clear();
    options.KnownProxies.Clear();
});
var app = builder.Build();

using (var scope = app.Services.CreateScope())
{
    var initializer = scope.ServiceProvider.GetRequiredService<IDatabaseInitializer>();
    await initializer.InitializeAsync();
}
app.UseForwardedHeaders();
app.UseApplicationStaticFiles();
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}
app.UseApplicationOpenApi();
app.UseCors("MyAllowSpecificOrigins");
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.UseHttpsRedirection();
app.Run();