using FluentValidation;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth.Validators
{
    public class UpdateUserRoleRequestValidator : AbstractValidator<UpdateUserRoleRequest>
    {
        public UpdateUserRoleRequestValidator()
        {
            RuleFor(x => x.Email)
                .NotEmpty().WithMessage("Email is required.")
                .EmailAddress().WithMessage("Invalid email format.");

            RuleFor(x => x.NewRole)
                .NotEmpty().WithMessage("New role is required.")
                .Must(role => role.Equals("user", StringComparison.OrdinalIgnoreCase) ||
                              role.Equals("admin", StringComparison.OrdinalIgnoreCase))
                .WithMessage("Invalid role. Allowed roles are: user, admin.");
        }
    }
}
