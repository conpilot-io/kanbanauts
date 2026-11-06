---
# Claude Code. Set KANBANAUTS_AI_API_KEY, KANBANAUTS_AI_MODEL, and optionally KANBANAUTS_AI_BASE_URL.
engine:
  id: claude
  env:
    ANTHROPIC_API_KEY: ${{ secrets.KANBANAUTS_AI_API_KEY }}
    ANTHROPIC_BASE_URL: ${{ vars.KANBANAUTS_AI_BASE_URL }}
model: ${{ vars.KANBANAUTS_AI_MODEL }}
sandbox:
  agent:
    token-steering: false
network:
  allowed:
    - defaults
    - github
    - "*.services.ai.azure.com"
    - "*.anthropic.com"
    - api.anthropic.com
---
<!-- Shared Claude engine for Kanbanauts. Override network.allowed for custom hosts. -->
