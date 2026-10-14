# ShopSense Deck Outline

This deck evolves with the repository milestone by milestone.

Keep one presentation file only:

```text
docs/deck/iith-ai-capstone-shopsense.pptx
```

Update the same deck for each milestone instead of creating milestone-specific copies.

## Current Scope

M1: Intake Parsing
M2: Safe Action Planning
M3: Customer Memory and Policy Index
M4: Grounded Policy RAG
M5: LangGraph Workflow
M6: Multi-Agent Team and MCP Tools
M7: Tracing and Reliability
M8: Golden Eval and FastAPI Packaging

## Slides (10, the maximum)

1 Title | 2 Problem | 3 End-to-end architecture
4 M1 + M2 | 5 M3 + M4 | 6 M5 + M6 | 7 M7 + M8
8 Walkthrough: safe refund vs risky refund | 9 Results, improvements, limits | 10 Demo plan and takeaways

## Rebuild

The deck is generated, so edit numbers in one place and rerun:

```bash
python docs/deck/build_deck.py
```

Needs `python-pptx`. Speaker notes are included on every slide.
