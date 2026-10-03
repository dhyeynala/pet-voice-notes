"""The LLM layer: schemas, versioned prompts, deterministic fake rules and the validating client.

The model reads; code decides. Every provider call goes through ``client.LLMClient``, which
renders a versioned prompt, validates the output against a Pydantic schema (one repair
retry), treats truncation as a failure and writes one ``llm_calls`` record per attempt.
"""
