using FluentValidation;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot.Validators
{
    public class AskCopilotRequestValidator : AbstractValidator<AskCopilotRequest>
    {
        public AskCopilotRequestValidator()
        {
            RuleFor(x => x.Question)
                .NotEmpty().WithMessage("Question is required and must not be empty.")
                .MaximumLength(1000).WithMessage("Question cannot exceed 1000 characters.");

            RuleFor(x => x.Conversation)
                .NotNull().WithMessage("Conversation list must be provided (can be empty).");

            RuleForEach(x => x.Conversation).ChildRules(message =>
            {
                message.RuleFor(m => m.Role)
                    .NotEmpty().WithMessage("Message role is required.")
                    .Must(role => role.Equals("user", System.StringComparison.OrdinalIgnoreCase) ||
                                  role.Equals("assistant", System.StringComparison.OrdinalIgnoreCase))
                    .WithMessage("Role must be either 'user' or 'assistant'.");

                message.RuleFor(m => m.Content)
                    .NotEmpty().WithMessage("Message content is required.");
            });
        }
    }
}
