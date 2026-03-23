"""
llm_client.py - Client astratto per provider AI (Cerebras, Claude, OpenAI)

Fornisce interfaccia unificata per chiamare diversi LLM provider.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Client astratto per provider AI multipli.

    Supporta:
        - Cerebras (gratuito, llama-3.3-70b)
        - Claude (Anthropic, claude-sonnet-4)
        - OpenAI (gpt-4o)
    """

    def __init__(self, provider: Optional[str] = None):
        """
        Inizializza client LLM.

        Args:
            provider: Nome provider ("cerebras", "claude", "openai")
                     Se None, legge da env AI_PROVIDER (default: cerebras)
        """
        self.provider = (provider or os.environ.get("AI_PROVIDER", "cerebras")).lower()
        self._validate_provider()

    def _validate_provider(self):
        """Valida provider e presenza API key."""
        if self.provider == "cerebras":
            self.api_key = os.environ.get("CEREBRAS_API_KEY")
            if not self.api_key:
                raise ValueError("CEREBRAS_API_KEY non configurata")
        elif self.provider == "claude":
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY non configurata")
        elif self.provider == "openai":
            self.api_key = os.environ.get("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY non configurata")
        else:
            raise ValueError(f"Provider non supportato: {self.provider}")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Genera completamento da prompt.

        Args:
            prompt: Prompt utente
            max_tokens: Token massimi generati
            temperature: Temperatura sampling (0.0-1.0)

        Returns:
            Dict con:
                - response_text: str - Testo generato
                - model_used: str - Modello usato
                - provider: str - Provider usato

        Raises:
            Exception: Se chiamata API fallisce
        """
        logger.info(f"Chiamata LLM provider: {self.provider}")

        if self.provider == "cerebras":
            return self._generate_cerebras(prompt, max_tokens, temperature)
        elif self.provider == "claude":
            return self._generate_claude(prompt, max_tokens, temperature)
        elif self.provider == "openai":
            return self._generate_openai(prompt, max_tokens, temperature)

    def _generate_cerebras(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        """Genera con Cerebras (API compatibile OpenAI)."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.cerebras.ai/v1"
        )

        completion = client.chat.completions.create(
            model="llama-3.3-70b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {
            "response_text": completion.choices[0].message.content,
            "model_used": "cerebras/llama-3.3-70b",
            "provider": "cerebras"
        }

    def _generate_claude(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        """Genera con Claude (Anthropic)."""
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "response_text": message.content[0].text,
            "model_used": "claude-sonnet-4-20250514",
            "provider": "claude"
        }

    def _generate_openai(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        """Genera con OpenAI."""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {
            "response_text": completion.choices[0].message.content,
            "model_used": "gpt-4o",
            "provider": "openai"
        }
