---
# Gemini CLI. Set KANBANAUTS_AI_API_KEY and KANBANAUTS_AI_MODEL.
engine:
  id: gemini
  env:
    GEMINI_API_KEY: ${{ secrets.KANBANAUTS_AI_API_KEY }}
model: ${{ vars.KANBANAUTS_AI_MODEL }}
network:
  allowed:
    - defaults
    - github
    - "*.googleapis.com"
    - generativelanguage.googleapis.com
---
<!-- Shared Gemini engine for Kanbanauts. -->
