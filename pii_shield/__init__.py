"""PII Shield: a span-based PII scrubber for text that is about to be sent to an LLM."""

from pii_shield.scrubber import PIIScrubber, ScrubResult, Shield

__all__ = ["PIIScrubber", "ScrubResult", "Shield"]
__version__ = "2.0.0"
