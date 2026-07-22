# LLM and Speech Gateway Contract

## Gateway boundary

Business modules depend on the following provider-neutral operations and never import a vendor SDK:

```python
class LLMGateway(Protocol):
    def chat(self, request: ChatRequest) -> ChatResponse: ...
    def structured(self, request: StructuredRequest[T]) -> T: ...
    def summarize(self, request: SummarizeRequest) -> TextResult: ...
    def classify(self, request: ClassifyRequest[T]) -> T: ...
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
    def understand_image(self, request: ImageUnderstandingRequest[T]) -> T: ...

class SpeechGateway(Protocol):
    def transcribe(self, request: TranscriptionRequest) -> TranscriptResult: ...
```

The protocols define domain requests, timeouts, cancellation and stable error categories. Adapters initially support
OpenAI, Anthropic and Ollama for LLM-compatible operations, and OpenAI Whisper, local faster-whisper and a generic
cloud speech adapter for transcription. Unsupported capabilities fail before work is queued.

## Scenario configuration

Each scenario has a separately versioned record:

| Field | Rule |
|---|---|
| `scenario` | One of the catalog keys below |
| `provider_key` / `model` | Logical provider route and model; no secret in DB |
| `prompt_version` | Immutable prompt asset version |
| `temperature` | 0..2; structured extraction defaults near 0 |
| `max_tokens` | Positive, bounded by deployment budget |
| `schema_version` | Required for structured scenarios |
| `timeout_seconds` | Per scenario hard limit |
| `max_retries` | Transient retries only; invalid schema uses bounded repair attempt |
| `cache_policy` | off, exact-input, or entity-version; never cache across users |

Catalog: `parse_voice_task`, `classify_capture`, `generate_capture_tags`, `estimate_task_duration`, `split_task`,
`generate_daily_plan`, `reschedule_tasks`, `analyze_habit`, `generate_blog`, `optimize_blog`, `summarize_day`,
`generate_weekly_review` (configured but weekly review UI is post-MVP).

## Strict validation flow

1. Application loads authorized entities and creates a bounded, provenance-aware input DTO.
2. Gateway selects provider/model/prompt/schema for the scenario and writes a pending LLM log.
3. Provider response is parsed with strict Pydantic (`extra='forbid'`) against the exact schema version.
4. One configured repair attempt may receive validation errors, never additional private entities.
5. If still invalid, job fails with a stable safe error and no business mutation.
6. Valid output is stored as a suggestion tied to source entity versions. Applying it uses the domain service and
   performs ownership, fixed-event and optimistic-version checks again.

## Schemas

- [voice-task.v1.json](schemas/voice-task.v1.json): transcription to confirmation card.
- [capture-analysis.v1.json](schemas/capture-analysis.v1.json): title/category/tag and uncertain fact suggestions.
- [schedule-preview.v1.json](schemas/schedule-preview.v1.json): concrete moves/deferrals/splits for preview only.

Assistant responses reuse versioned domain card DTOs from OpenAPI. Free-form chat text may accompany cards but never
represents an executable action.

## Safety and provenance rules

- Prompts state that missing data must remain null/empty and must not be invented.
- Input entity refs include ID and version; output can reference only the supplied IDs.
- `reschedule_tasks` input excludes secrets and marks fixed events. Output mentioning a fixed event must use `keep`
  and `selectable=false`; the apply service rejects any violation regardless of schema validity.
- Capture facts are suggestions with confidence and evidence summary. They never populate `*_user` columns.
- Voice dates/times are interpreted in the supplied user timezone and include that timezone in the output; user
  confirmation is still mandatory.
- Blog generation creates an unapplied AI revision. Prompt injection inside a capture or blog source is treated as
  user content, not system instruction.
- LLM logs store usage, latency, cost, status, scenario and entity refs. Full prompt/output logging is off by default.

## Stable provider errors

`provider_unavailable`, `timeout`, `rate_limited`, `authentication_failed`, `content_rejected`,
`capability_unsupported`, `invalid_structured_output`, `budget_exceeded`, `cancelled`.

Only unavailable, timeout and rate-limited are retryable by default. Authentication/capability/budget errors require
configuration changes; invalid output receives at most the configured repair attempt.
