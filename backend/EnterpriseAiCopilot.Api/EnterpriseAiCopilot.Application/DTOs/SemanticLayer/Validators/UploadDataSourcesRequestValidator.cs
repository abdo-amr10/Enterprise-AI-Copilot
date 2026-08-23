using FluentValidation;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer.Validators
{
    public class UploadDataSourcesRequestValidator : AbstractValidator<UploadDataSourcesRequest>
    {
        public UploadDataSourcesRequestValidator()
        {
            RuleFor(x => x.Name)
                .NotEmpty().WithMessage("Name is required.")
                .MaximumLength(100).WithMessage("Name must not exceed 100 characters.");

            RuleFor(x => x.Description)
                .NotEmpty().WithMessage("Description is required.")
                .MaximumLength(500).WithMessage("Description must not exceed 500 characters.");

            RuleFor(x => x.SchemaFile)
                 .Cascade(CascadeMode.Stop)
                 .NotNull().WithMessage("Schema file is required.")
                 .Must(file => file.Length > 0).WithMessage("Schema file cannot be empty.")
                 .Must(file => file.FileName.EndsWith(".sql", StringComparison.OrdinalIgnoreCase) ||
                               file.FileName.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase) ||
                               file.FileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) 
                 .WithMessage("Schema file must be a .sql, .pdf, or .json file."); 


            When(x => x.DocumentationFile != null, () =>
            {
                RuleFor(x => x.DocumentationFile!)
                    .Must(file => file.Length > 0).WithMessage("Documentation file cannot be empty.");
            });

            When(x => x.GlossaryFile != null, () =>
            {
                RuleFor(x => x.GlossaryFile!)
                    .Must(file => file.Length > 0).WithMessage("Glossary file cannot be empty.");
            });

            When(x => x.SampleDataFile != null, () =>
            {
                RuleFor(x => x.SampleDataFile!)
                    .Must(file => file.Length > 0).WithMessage("SampleData file cannot be empty.")
                    .Must(file => file.FileName.EndsWith(".csv", StringComparison.OrdinalIgnoreCase))
                    .WithMessage("SampleData file must be a .csv file.");
            });
        }
    }
}
