import ollama

response = ollama.generate(
    model="qwen2.5-coder:7b",
    prompt="""
Return ONLY valid JSON.

Use exactly this structure:
{
  "status": "success",
  "sql": "SELECT 1;",
  "is_read_only": true
}

Do not use markdown.
Do not add any explanation.
"""
)

print("RAW RESPONSE:")
print(repr(response.response))