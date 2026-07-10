"""LLM provider adapters.

The self-hosted runtime owns orchestration. Modules here may call providers and
return text/JSON plus usage metadata, but they must not route agents, execute
tools, persist traces, or decide handoffs.
"""
