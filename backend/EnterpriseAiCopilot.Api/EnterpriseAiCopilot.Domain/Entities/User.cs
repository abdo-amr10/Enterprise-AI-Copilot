using EnterpriseAiCopilot.Domain.Common;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class User : BaseEntity
    {
        public string FirstName { get; set; } = string.Empty;
        public string LastName { get; set; } = string.Empty;
        public string Email { get; set; } = string.Empty;
        public string PasswordHash { get; set; } = string.Empty;
        public string Role { get; set; } = "User"; // "Admin" | "User"
        public string? BranchId { get; set; }

    }
}
