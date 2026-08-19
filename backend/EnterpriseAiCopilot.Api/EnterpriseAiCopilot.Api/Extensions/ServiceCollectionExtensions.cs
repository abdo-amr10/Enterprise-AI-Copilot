using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Infrastructure.Identity;
using EnterpriseAiCopilot.Infrastructure.Identity.Services;
using EnterpriseAiCopilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

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
            return services;
        }
    }
}
