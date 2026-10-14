# M1 Intake: sequence diagram

Source: `src/capstone/agents/intake_agent.py` (`parse_ticket`) and `src/capstone/llm/client.py` (`LLMClient.structured`).

Design rule: the LLM understands the language; plain code makes every rule-based decision and has the last word.

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant P as parse_ticket (code)
    participant L as LLMClient
    participant M as LLM (Gemini or Groq via LiteLLM)

    C->>P: raw text + channel
    P->>P: truncate to 6000 chars
    P->>L: system prompt (intake.md) + wrapped text in ticket tags
    loop until schema-valid, up to the retry limit
        L->>M: request JSON in SupportTicket shape, temperature 0
        M-->>L: JSON reply
        alt invalid JSON or schema violation
            L->>M: the validation error, asking for corrected JSON
        else valid
            L-->>P: SupportTicket (model's draft)
        end
    end
    Note over L,M: 429 rate limit: wait, double the delay, retry.<br/>Other provider failure: raise LLMError (nothing is guessed).

    rect rgb(255, 240, 240)
    Note over P: Code overrides the model (the model cannot decide these)
    P->>P: 1. Order ID must appear literally in the text, else replaced or set to null and listed as missing
    P->>P: 2. Regex injection screen (English, Hinglish, fake system tags). Can only turn the flag ON
    P->>P: 3. Delete the model's refund_above_auto_cap and repeat_contact signals
    P->>P: 4. Recompute them: claimed amount > cap? contact number >= threshold?
    end

    P-->>C: validated SupportTicket (typed object for M2 onward)
```

## Reading it

| Steps | Who | What |
|---|---|---|
| 1-3 | Code | Take the text, cap its size, wrap it so the model treats it as data |
| 4-7 | LLM client and model | Ask for JSON in the exact schema; retry with the error if invalid |
| 8-11 | Code | Order ID check, injection regex, cap and repeat-contact arithmetic |
| 12 | Code | Hand a typed `SupportTicket` to the next module |

## Example (hostile message)

| Stage | `escalation_signals` | `prompt_injection_suspected` |
|---|---|---|
| Model draft | `[angry_or_abusive]` | true |
| After code checks | `[angry_or_abusive, refund_above_auto_cap]` | true (also confirmed by the regex) |
