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

## Slides (9 of the 10 allowed)

1 Title + the one job | 2 End-to-end architecture
3 M1 sequence (shapes, one sample) | 4 M2 sequence (same sample) + three cases strip
5 M3 + M4 | 6 M5 + M6 | 7 M7 + M8
8 Results, improvements, limits | 9 Demo plan and takeaways

The sample carried through M1 and M2: customer KW-C-00317, order KW-O-000000, claim Rs 12,999.
Full Mermaid diagrams: `docs/diagrams/`.

## Rebuild

The deck is generated, so edit numbers in one place and rerun:

```bash
python docs/deck/build_deck.py
```

Needs `python-pptx`. Speaker notes are included on every slide.
