"""Secret providers for local and Azure Key Vault."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class EnvSecretProvider:
    """Read secrets from environment variables (optionally with a prefix)."""

    prefix: str = ""
    mapping: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        if name in self.mapping:
            return self.mapping[name]
        key = f"{self.prefix}{name}" if self.prefix else name
        # Also try SCREAMING_SNAKE aliases
        aliases = [
            key,
            key.upper().replace("-", "_"),
            name.upper().replace("-", "_"),
        ]
        for alias in aliases:
            value = os.environ.get(alias)
            if value:
                return value
        raise KeyError(f"Secret not found: {name}")


@dataclass(slots=True)
class AzureKeyVaultSecretProvider:
    """Read secrets from Azure Key Vault using DefaultAzureCredential."""

    vault_url: str
    _cache: dict[str, str] = field(default_factory=dict, repr=False)

    def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=self.vault_url, credential=DefaultAzureCredential())
        secret = client.get_secret(name)
        value = secret.value or ""
        self._cache[name] = value
        return value
