using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace EnterpriseAiCopilot.Infrastructure.Persistence;

public sealed class DatabaseSeeder
{
    private const string DefaultAdminEmail = "admin@copilot.com";
    private const string DefaultAdminPassword = "P@ssw0rd";

    private readonly ApplicationDbContext _context;
    private readonly IConfiguration _configuration;
    private readonly ILogger<DatabaseSeeder> _logger;

    public DatabaseSeeder(
        ApplicationDbContext context,
        IConfiguration configuration,
        ILogger<DatabaseSeeder> logger)
    {
        _context = context;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task SeedAdminAsync(CancellationToken cancellationToken = default)
    {
        var email = (_configuration["SeedAdmin:Email"] ?? DefaultAdminEmail).Trim().ToLowerInvariant();
        var password = _configuration["SeedAdmin:Password"] ?? DefaultAdminPassword;

        if (!await _context.Users.AnyAsync(user => user.Email == email, cancellationToken))
        {
            _context.Users.Add(new User
            {
                FirstName = _configuration["SeedAdmin:FirstName"] ?? "Copilot",
                LastName = _configuration["SeedAdmin:LastName"] ?? "Administrator",
                Email = email,
                PasswordHash = BCrypt.Net.BCrypt.HashPassword(password),
                Role = "admin",
                BranchId = null,
                CreatedBy = "SYSTEM"
            });

            await _context.SaveChangesAsync(cancellationToken);
            _logger.LogInformation("Default administrator account was created for {Email}.", email);
        }
    }
}
