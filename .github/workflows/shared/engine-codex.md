---
# Codex / OpenAI. Set KANBANAUTS_AI_API_KEY, KANBANAUTS_AI_MODEL, and optionally KANBANAUTS_AI_BASE_URL.
engine:
  id: codex
  env:
    OPENAI_API_KEY: ${{ secrets.KANBANAUTS_AI_API_KEY }}
    # Default keeps baseUrlEnv valid when the org var is unset (public OpenAI).
    OPENAI_BASE_URL: ${{ vars.KANBANAUTS_AI_BASE_URL || 'https://api.openai.com/v1' }}
model: ${{ vars.KANBANAUTS_AI_MODEL }}
network:
  allowed:
    - defaults
    - github
    - "*.openai.azure.com"
    - "*.openai.com"
    - api.openai.com
---
<!-- Shared Codex engine for Kanbanauts. Override network.allowed for custom hosts. -->
