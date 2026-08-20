using EnterpriseAiCopilot.Api.Extensions;
using EnterpriseAiCopilot.API.Middlewares;
using EnterpriseAiCopilot.Application;
using FluentValidation.AspNetCore;
using Microsoft.OpenApi;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    options.SwaggerDoc("v1", new OpenApiInfo
    {
        Title = "EnterpriseAiCopilot.Api",
        Version = "v1"
    });

    options.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Name = "Authorization",
        Type = SecuritySchemeType.Http,
        Scheme = "Bearer",
        BearerFormat = "JWT",
        In = ParameterLocation.Header,
        Description = "Enter your JWT token"
    });

    options.AddSecurityRequirement(document => new OpenApiSecurityRequirement
    {
        [new OpenApiSecuritySchemeReference("Bearer", document)] = []
    });
});
// Module 0 DI Registrations
builder.Services.AddInfrastructureServices(builder.Configuration);
builder.Services.AddJwtAuthentication(builder.Configuration);
builder.Services.AddCustomAuthorization();
builder.Services.AddApplicationServices();

// Global Exception Handler + Problem Details
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
builder.Services.AddProblemDetails();

// التعديل 1: إضافة خدمة الـ Cache عشان اللوج اوت يشتغل
builder.Services.AddDistributedMemoryCache();

var app = builder.Build();

// التعديل 2: الاعتماد على الـ Exception Handler الجديد فقط
app.UseExceptionHandler();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// ترتيب الـ Pipeline الأمني بدقة
app.UseAuthentication();

// التعديل 3: إضافة حارس القائمة السوداء هنا بالظبط
app.UseMiddleware<TokenBlacklistMiddleware>();

app.UseAuthorization();

app.MapControllers();

app.Run();