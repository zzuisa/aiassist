# Research: Agent 首屏与文章结果交互

## Decision: Start with no active conversation

**Rationale**: Restoring the most recent active conversation creates an unexpected wall of unrelated history. Deferring conversation creation until the first send preserves persistence without making history the default UI.

**Alternatives considered**:

- Archive prior conversations automatically: rejected because it mutates user history merely on page open.
- Show collapsed history: rejected for v1 because it still distracts from the primary start action.

## Decision: Reuse existing private article route

**Rationale**: It centralizes ownership enforcement and avoids exposing raw result data or building a second article viewer.

**Alternatives considered**:

- Inline full article preview: rejected because it duplicates the reader and adds substantial rendering/privacy complexity.

## Decision: Render safe result cards only

**Rationale**: Article cards provide a clear next action while displaying only titles and optional existing public-to-owner metadata.

**Alternatives considered**:

- Render arbitrary task-result JSON: rejected because it leaks internal representation and is not a usable interaction.
