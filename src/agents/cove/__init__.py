"""Chain-of-Verification (CoVe) anti-hallucination pipeline.

Five-phase verification:
1. Draft generation - initial LLM response
2. Verification planning - generate verification questions per claim
3. Independent execution - verify each claim in isolated context
4. Final revision - correct draft based on verification results
5. Citation validation - check every URN/CELEX via Normattiva/EUR-Lex API
"""
