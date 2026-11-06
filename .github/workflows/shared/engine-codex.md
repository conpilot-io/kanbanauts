---
# Codex / OpenAI. Set KANBANAUTS_AI_API_KEY, KANBANAUTS_AI_MODEL, and optionally KANBANAUTS_AI_BASE_URL.
engine:
  id: codex
  env:
    OPENAI_API_KEY: ${{ secrets.KANBANAUTS_AI_API_KEY }}
    OPENAI_BASE_URL: ${{ vars.KANBANAUTS_AI_BASE_URL }}
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
