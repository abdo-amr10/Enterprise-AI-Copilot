using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Services;
using EnterpriseAiCopilot.Infrastructure.Data;
using EnterpriseAiCopilot.Infrastructure.ExternalServices;
using EnterpriseAiCopilot.Infrastructure.FileStorage;
using EnterpriseAiCopilot.Infrastructure.Identity;
using EnterpriseAiCopilot.Infrastructure.Identity.Services;
using EnterpriseAiCopilot.Infrastructure.Persistence;
using EnterpriseAiCopilot.Api.Contracts.Copilot;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace EnterpriseAiCopilot.Api.Extensions
{
    public static class ServiceCollectionExtensions
    {
        public static IServiceCollection AddInfrastructureServices(this IServiceCollection services, IConfiguration configuration)
        {
            services.AddDbContext<ApplicationDbContext>(options =>
                options.UseSqlServer(configuration.GetConnectionString("DefaultConnection")));

            services.AddScoped<IApplicationDbContext>(provider => provider.GetRequiredService<ApplicationDbContext>());
            services.AddHttpContextAccessor();
            services.AddScoped<ICurrentUserService, CurrentUserService>();
            services.AddScoped<IAuthService, AuthService>();
            services.AddScoped<IFileStorage, LocalFileStorage>();
            services.AddScoped<ISemanticLayerService, SemanticLayerService>();
            services.AddScoped<ICopilotService, CopilotService>();
            services.AddScoped<IDynamicSqlExecutor, DynamicSqlExecutor>();
            services.AddHttpClient<IAiRuntimeClient, AiRuntimeHttpClient>();
            services.AddHttpClient<IAiSemanticClient, AiSemanticHttpClient>();
            services.AddScoped<IAuditService, AuditService>();
            services.AddHttpClient<IAiResultFormatterClient, AiResultFormatterHttpClient>();
            services.AddOptions<AiRuntimeOptions>()
                .Bind(configuration.GetSection(AiRuntimeOptions.SectionName))
                .Validate(options => Uri.TryCreate(options.BaseUrl, UriKind.Absolute, out _),
                    "AiRuntime:BaseUrl must be an absolute URL.")
                .Validate(options => options.TimeoutSeconds > 0,
                    "AiRuntime:TimeoutSeconds must be positive.");
           
            return services;
        }
    }
}
