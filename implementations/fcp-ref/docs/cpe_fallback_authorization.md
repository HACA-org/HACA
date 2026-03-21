# CPE Fallback Chain Authorization & Transparency

**Date:** 2026-03-21
**Status:** Design documentation

---

## Overview

Fallback chains enable graceful degradation when adapters fail. This document clarifies authorization patterns, transparency requirements, and user notification.

---

## Design Philosophy

### Core Principle: Resilience > Confirmation

Fallback chains prioritize **keeping the system running** over requiring explicit user confirmation for each fallback. This aligns with the CPE design goal of transparent adaptation.

**Rationale:**
- User started session with FCP (implicit consent to use CPE adapters)
- All adapters in chain meet user's quality requirements (pre-selected)
- Blocking on confirmation defeats resilience purpose
- Notification (not confirmation) keeps user informed

---

## Authorization Models

### Model 1: Silent Fallback (Default)

**Behavior:**
```python
chain = FallbackChain([("openai", openai), ("anthropic", anthropic)])
response, adapter = chain.invoke(system, messages, tools)
# If OpenAI fails, silently uses Anthropic
```

**Transparency:**
- No callback notification
- Failures logged (grep logs to see fallback events)
- User may notice response comes from different model/provider
- Suitable for backend services, automated systems

**When to Use:**
- Unattended sessions (cron, CMI delegates)
- Internal tools where resilience > transparency
- High-reliability requirements

---

### Model 2: Notified Fallback (Recommended for UI)

**Behavior:**
```python
def on_fallback(primary, fallback_to, error):
    ui.show_banner(f"Switched from {primary} to {fallback_to}")

chain = FallbackChain(
    [("openai", openai), ("anthropic", anthropic)],
    notify_callback=on_fallback,
)
response, adapter = chain.invoke(system, messages, tools)
```

**Transparency:**
- User sees fallback notification (banner/toast)
- Operator is informed provider/model changed
- Still transparent (no blocking confirmation)
- Suitable for interactive sessions (Telegram, UI)

**When to Use:**
- User-facing interfaces (TUI, web, mobile)
- Sessions where user is actively engaged
- Primary requirement: visibility + resilience

---

### Model 3: Opt-Out Fallback (Strict Control)

**Behavior:**
```python
class StrictFallback:
    def __init__(self, adapters, operator):
        self.chain = FallbackChain(adapters, notify_callback=self.ask_approval)
        self.operator = operator

    def ask_approval(self, primary, fallback_to, error):
        approved = self.operator.ask_yes_no(
            f"OpenAI failed. Switch to {fallback_to}?"
        )
        if not approved:
            raise CPEError(f"User rejected fallback to {fallback_to}")

chain = StrictFallback([("openai", openai), ("anthropic", anthropic)], operator)
response, adapter = chain.invoke(system, messages, tools)
```

**Transparency:**
- Explicit user consent for fallback
- Blocks until user responds
- Defeats resilience goal
- Suitable only for critical operations

**When to Use:**
- VERY rare (contradicts CPE resilience philosophy)
- Perhaps: medical/legal decisions requiring audit trail
- Not recommended for normal operation

---

## Recommended Patterns by Session Type

| Session Type | Pattern | Rationale |
|--------------|---------|-----------|
| main:session + UI | Notified | User present, wants visibility |
| auto:session | Silent | Unattended, resilience priority |
| Telegram bot | Notified | User present, asynchronous |
| cron job | Silent | No operator, resilience only |
| CMI delegate | Silent | Background task, keep running |

---

## Implementation Details

### Notification Callback Contract

```python
def notify_callback(
    primary: str,      # Name of primary adapter that failed
    fallback_to: str,  # Name of fallback adapter being used
    error: str,        # Error message from primary adapter
) -> None:
    """Called when fallback occurs.

    Exceptions in callback are logged but don't break fallback chain.
    Callback is NOT blocking (fire-and-forget).
    """
    pass
```

**Important:** Callback WILL NOT fire if:
- Primary adapter succeeds (no fallback needed)
- All adapters fail (different error raised)

---

### Fallback Event Tracking

All fallback chains track events for analytics/debugging:

```python
chain = FallbackChain([...])
chain.invoke(system, messages, tools)

# Later, examine what happened
summary = chain.get_fallback_summary()
# {
#     "total_fallbacks": 2,
#     "primary_adapter": "openai",
#     "fallback_events": [
#         {"primary_adapter": "openai", "fallback_to": "anthropic", "attempt": 1},
#         {"primary_adapter": "openai", "fallback_to": "ollama", "attempt": 2}
#     ]
# }
```

**Use Cases:**
- Audit trail (what adapters were tried)
- Monitoring (fallback frequency alerts)
- Cost tracking (which adapter actually ran)
- SLA verification (fallback count)

---

## Security Considerations

### Does fallback chain leak API keys?

**No.** Each adapter's API key is isolated:
- OpenAI API key never passed to Anthropic adapter
- Anthropic API key never passed to Ollama
- Fallback mechanism only changes *which* adapter runs, not credentials

### Can fallback bypass authorization gates?

**No.** All adapters in chain are pre-authorized:
- User explicitly constructs chain with approved adapters
- User chooses adapters that meet their requirements
- Fallback doesn't introduce new adapters or capabilities

### What if fallback changes response behavior?

**Possible but mitigated:**
- Different adapters have slightly different output styles
- All adapters in chain should be similar quality (user responsibility)
- Notification callback makes user aware of switch
- If critical: use Model 3 (strict confirmation)

---

## Best Practices

1. **Chain Similar-Quality Adapters**
   ```python
   # Good: All are capable
   FallbackChain([
       ("openai", OpenAIAdapter("gpt-4o")),
       ("anthropic", AnthropicAdapter("claude-opus")),
       ("ollama", OllamaAdapter("llama3.2")),
   ])

   # Bad: Includes inferior models
   FallbackChain([
       ("openai", OpenAIAdapter("gpt-4o")),
       ("ollama", OllamaAdapter("tinyllama")),  # Don't do this
   ])
   ```

2. **Use Notification for User-Facing Sessions**
   ```python
   if is_main_session():
       chain = FallbackChain(adapters, notify_callback=ui.alert_user)
   else:
       chain = FallbackChain(adapters)  # Silent fallback
   ```

3. **Monitor Fallback Frequency**
   ```python
   chain.invoke(...)
   summary = chain.get_fallback_summary()
   if summary["total_fallbacks"] > 10:
       logger.warning("High fallback frequency detected")
   ```

4. **Log for Debugging**
   ```python
   # All failures logged automatically
   # Check logs to see why primary adapter failed
   grep "FallbackChain" logs/ | grep "WARNING"
   ```

---

## Migration Path

### Current State (Phase 5)
- Fallback chains implemented with optional notifications
- Default: silent fallback (backward compatible)
- Notification via callback (opt-in)

### Future (Phase 6+)
- Integration with session loop for automatic notification
- Cost tracking shows which adapter actually executed
- Adaptive selection may prefer fallback adapters based on cost
- UI hooks for real-time fallback visibility

---

## FAQ

**Q: Does fallback chain require user confirmation?**
A: No (by design). Confirmation blocks resilience. Use notification callback for visibility.

**Q: What if user doesn't want fallback to specific adapter?**
A: Don't include that adapter in the chain. Fallback respects the chain order you specify.

**Q: How do I know which adapter was used?**
A: `invoke()` returns `(response, adapter_name)`. Also check `chain.get_fallback_summary()`.

**Q: Does fallback affect cost tracking?**
A: Yes. Cost tracker records whichever adapter actually executed (not primary).

**Q: Can fallback change the response significantly?**
A: Possible. Different models have different styles. Mitigate by chaining similar-quality adapters.

**Q: Is fallback transparent to the user?**
A: Default: no. With notification callback: yes. Choice is yours.

---

## Conclusion

Fallback chains enable **resilience without requiring confirmation**, aligned with CPE's design philosophy. Notification callbacks provide **transparency for user-facing sessions** without blocking.

**Recommendation:** Use notified fallback for all user-facing sessions; silent fallback for background tasks.
