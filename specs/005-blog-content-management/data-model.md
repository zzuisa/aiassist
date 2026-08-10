# Data Model: 个人信息总站博客内容管理扩展

**Feature**: `005-blog-content-management`  
**Date**: 2026-07-28  
**Migration**: `backend/alembic/versions/0011_blog_content_management.py`

## Modeling Principles

1. `Post` remains the article aggregate root and current-state projection.
2. Every accepted content change creates an immutable `PostRevision` snapshot.
3. Original inputs live in `PostSource`; they are never inferred from edited content.
4. AI execution (`PostAIRun`), generated snapshot (`PostRevision`), and review state (`PostAICandidate`) are separate.
5. Skill identity is editable; Skill versions are immutable and tasks bind one fixed version.
6. Core filter fields are relational; content-type-specific values use validated JSONB.
7. Every user-owned relation repeats `user_id` where it supports ownership filtering and integrity checks.
8. Derived search and word-cloud data are rebuildable and never the authorization source.

## Existing Entity Changes

### Post (`posts`)

Current article projection. Existing public fields remain compatible.

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Existing primary key |
| `user_id` | UUID | Existing owner FK, required |
| `slug` | string? | Existing published slug semantics unchanged |
| `title` | string | Required, max 240 |
| `subtitle` | string? | Max 240 |
| `summary` | text? | Max 2,000; replaces neither existing excerpt nor SEO fields |
| `markdown` | text | Canonical current body, max 200,000 for MVP |
| `status` | string | Existing `draft/private/published`; not reused for internal workflow |
| `content_status` | string | `pending_capture/pending_parse/triage/draft/ai_queued/ai_processing/ai_review/merge_required/completed/archived/discarded` |
| `content_class` | string | Stable key: `technical/project/learning/life/travel/diary/essay/bookmark/media/item/quick` |
| `content_type_id` | UUID? | FK to `post_content_types`, owner and class must match |
| `category_id` | UUID? | FK to existing `categories`; must be owned and `kind=post` |
| `language` | string | BCP-47-like bounded key, default user locale |
| `editor_mode` | string | `markdown/rich/split`, per-article last mode |
| `occurred_at` | timestamptz? | Content occurrence time |
| `location_text` | string? | Max 240, searchable |
| `project_text` | string? | Max 240, searchable |
| `structured_data_json` | JSONB | Validated against active content-type schema; unknown historical keys preserved |
| `current_revision_id` | UUID | Existing pointer; becomes required after backfill |
| `latest_ai_status` | string? | Denormalized display status only |
| `first_ai_optimized_at` | timestamptz? | First completed optimization |
| `last_ai_optimized_at` | timestamptz? | Most recent terminal optimization |
| `ai_optimization_count` | integer | Non-negative, default 0 |
| `last_skill_version_id` | UUID? | Informational pointer, not task execution source |
| `version` | integer | Existing optimistic lock, increment on current projection changes |
| `deleted_at` | timestamptz? | Existing soft delete |
| existing public/SEO fields | existing | Unchanged |

**Indexes**:

- `(user_id, content_status, updated_at desc)`
- `(user_id, content_class, content_type_id, updated_at desc)`
- `(user_id, occurred_at desc)` where not deleted
- `(user_id, category_id)` where not deleted
- GIN on `structured_data_json` for containment filters if performance tests justify it
- Existing published slug and publication indexes remain

**Rules**:

- `status` and `content_status` change independently.
- Current columns must equal `current_revision_id.snapshot_json` for fields owned by the revision.
- A new Post always has a first applied revision before commit.
- Changing content type never deletes unknown `structured_data_json` keys.

### PostRevision (`post_revisions`)

Immutable complete article snapshot.

| Field | Type | Rules |
|---|---|---|
| existing identity/owner/post fields | existing | Retained |
| `parent_revision_id` | UUID? | Parent snapshot; owner/post must match |
| `base_revision_id` | UUID? | AI comparison base; null for normal user revisions |
| `source` | string | Expanded to `capture/user_edit/ai_candidate/ai_applied/restore/import/merge` |
| `revision_number` | integer | Monotonic per Post, unique `(post_id, revision_number)` |
| `markdown` | text | Snapshot body retained for compatibility |
| `snapshot_json` | JSONB | Complete restorable fields, schema version included |
| `change_summary` | string? | Max 500 |
| `async_job_id` | UUID? | Generic job reference |
| `skill_version_id` | UUID? | Fixed version when AI-related |
| `schema_version` | string | `post-revision.v1` initially |
| `applied_at` | timestamptz? | Non-null only when it became current |
| `created_at` | timestamptz | Immutable |

**Rules**:

- Rows are append-only; only `applied_at` may be set once for legacy compatibility.
- `snapshot_json` is validated before insert and cannot contain source raw bytes.
- Applying an AI candidate creates a new `ai_applied` revision; the original candidate remains unchanged.

### UploadSession (`upload_sessions`)

- Existing purposes `attachment` and `post_cover` are reused for user uploads.
- Add `post_source_snapshot` only if server-produced snapshots use the upload lifecycle; otherwise snapshots are written through the storage gateway and referenced by `PostSource.snapshot_object_key`.
- No public asset URL or server path is stored in article content.

## New Content Entities

### PostSource (`post_sources`)

One immutable-origin record per capture input; processing fields may advance.

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner FK |
| `post_id` | UUID | Required for accepted source; Post owner must match |
| `source_type` | string | `blank/clipboard/url/quick/template/file` |
| `status` | string | `saved/pending/processing/partial/completed/failed/cancelled` |
| `detected_format` | string? | `plain/markdown/html/rich/url/code/image/mixed` |
| `original_url` | text? | Normalized http/https URL, max 4,096 |
| `source_site` | string? | Max 240 |
| `source_author` | string? | Max 240 |
| `source_published_at` | timestamptz? | Extracted, never overwrites article occurrence time |
| `original_title` | text? | Max 1,000 |
| `original_text` | text? | Bounded accepted source content |
| `normalized_markdown` | text? | Sanitized extraction/normalization result |
| `user_note` | text? | Max 10,000 |
| `metadata_json` | JSONB | Language, links, image refs, partial-field markers |
| `snapshot_object_key` | string? | Private storage key, never exposed directly |
| `content_hash` | string? | SHA-256 of accepted original representation |
| `fetch_attempt_count` | integer | Non-negative |
| `error_code/message` | string? | Stable business error and bounded message |
| `async_job_id` | UUID? | Latest extraction job |
| `captured_at/fetched_at/extracted_at` | timestamptz | Applicable lifecycle timestamps |
| `created_at/updated_at` | timestamptz | Audit timestamps |

**Indexes/constraints**:

- `(user_id, status, created_at desc)`
- `(user_id, post_id, created_at)`
- `(user_id, original_url)` partial where URL not null
- `source_type=url` requires `original_url`
- Source raw content cannot be changed after first successful save; a new recapture creates another source.

### PostContentType (`post_content_types`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `content_class` | string | One stable article class |
| `key` | string | Stable per-user key |
| `name/description` | string | Name required, description optional |
| `field_schema_json` | JSONB | Definitions: key, label, type, required, order, validation, AI policy ceiling |
| `schema_version` | integer | Increment when definitions change |
| `sort_order` | integer | Stable display order |
| `enabled` | boolean | Disabled types remain readable historically |
| `is_system_seed` | boolean | Initial type flag, still user-configurable within allowed rules |
| `created_at/updated_at` | timestamptz | Audit timestamps |

**Unique**: `(user_id, key)` and `(user_id, content_class, lower(name))`.

## Taxonomy Entities

### PostCategoryProfile (`post_category_profiles`)

Extension for existing `Category(kind=post)`.

| Field | Type | Rules |
|---|---|---|
| `category_id` | UUID | PK/FK Category |
| `user_id` | UUID | Same owner as Category |
| `parent_category_id` | UUID? | Must be same user, kind post; bounded depth (default max 3) |
| `description` | string? | Max 500 |
| `sort_order` | integer | Default 0 |
| `enabled` | boolean | Disabled remains on old Posts |

Cycles are rejected before save. Merge is performed through `TaxonomyMerge`.

### PostTagProfile (`post_tag_profiles`)

| Field | Type | Rules |
|---|---|---|
| `tag_id` | UUID | PK/FK Tag |
| `user_id` | UUID | Same owner as Tag |
| `color` | string? | Valid semantic/color token, not raw style injection |
| `description` | string? | Max 500 |
| `enabled` | boolean | Disabled remains historical |

### PostTagAlias (`post_tag_aliases`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `tag_id` | UUID | Canonical Tag |
| `alias` | string | Case-insensitive unique per user, max 64 |

Aliases resolve to one canonical tag; an alias cannot collide with another canonical Tag name.

### PostKeyword (`post_keywords`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `canonical_text` | string | Case-insensitive unique, max 120 |
| `description` | string? | Max 500 |
| `enabled` | boolean | Disabled excluded from new suggestions/word cloud |
| `is_stop_word` | boolean | Excluded from word cloud and optional indexing |
| `created_at/updated_at` | timestamptz | Audit timestamps |

### PostKeywordAlias (`post_keyword_aliases`)

- `id`, `user_id`, `keyword_id`, `alias`; case-insensitive unique per user.
- Alias merge resolves input to canonical keyword but does not rewrite historical revision snapshots.

### PostKeywordLink (`post_keyword_links`)

| Field | Type | Rules |
|---|---|---|
| `post_id/keyword_id` | UUID | Composite PK |
| `user_id` | UUID | Owner repeated |
| `source` | string | `user/ai/recomputed/import` |
| `weight` | numeric | 0..1, optional ranking signal |
| `created_at` | timestamptz | Link time |

### TaxonomyMerge (`post_taxonomy_merges`)

Append-only record with `kind=category/tag/keyword`, source ID, target ID, affected count, user, status, job ID, timestamps and error summary. Source item is disabled only after all current relationships are redirected successfully.

## Skill Entities

### BlogSkill (`blog_skills`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `name` | string | Case-insensitive unique among non-deleted skills, max 120 |
| `description` | string? | Max 1,000 |
| `enabled` | boolean | New tasks require true |
| `current_version_id` | UUID | Must belong to Skill |
| `created_at/updated_at/deleted_at` | timestamptz | Soft delete; referenced versions retained |

### BlogSkillVersion (`blog_skill_versions`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id/skill_id` | UUID | Owner and parent |
| `version_number` | integer | Positive, unique per Skill |
| `config_json` | JSONB | Must validate `blog-skill-config.v1` |
| `schema_version` | string | Initial `blog-skill-config.v1` |
| `recommended_model` | string? | Stable configured model key, not secret |
| `max_content_chars` | integer | Bounded safe range |
| `long_content_strategy` | string | `reject/chunk/summarize_then_process` |
| `change_summary` | string? | Max 500 |
| `created_at` | timestamptz | Immutable |

No update/delete is allowed after insert while referenced.

### BlogSkillDefault (`blog_skill_defaults`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `scope_type` | string | `global/content_class/content_type` |
| `scope_key` | string | `global`, class key, or content-type UUID text |
| `skill_id` | UUID | Must be owned/enabled with valid current version |
| `created_at/updated_at` | timestamptz | Audit timestamps |

**Unique**: `(user_id, scope_type, scope_key)`. Resolution reads current version only at task submission.

## AI Entities

### PostAIRun (`post_ai_runs`)

One-to-one extension of a generic `AsyncJob`.

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `async_job_id` | UUID | Unique FK AsyncJob |
| `post_id` | UUID | Target article |
| `base_revision_id` | UUID | Fixed submitted revision |
| `optimization_type` | string | `full/language/structure/metadata/check/reoptimize` |
| `content_class` | string | Frozen submission value |
| `content_type_id` | UUID? | Frozen reference |
| `skill_version_id` | UUID | Fixed immutable Skill version |
| `model_key` | string | Fixed route key, no secret |
| `ai_schema_version` | string | `blog-optimization.v1` |
| `field_policy_json` | JSONB | Frozen effective policy after safety ceiling |
| `protected_tokens_json` | JSONB? | Hashes/types/locations, not duplicate raw article |
| `input_hash` | string | Detect exact duplicate request |
| `candidate_id` | UUID? | Set after candidate save |
| `outcome` | string? | `complete/partial/failed/timeout/cancelled` |
| `validation_summary_json` | JSONB? | Safe field-level codes and counts |
| `created_at/started_at/completed_at` | timestamptz | Run timestamps |

**Unique/indexes**:

- Unique `async_job_id`.
- Partial unique active request `(user_id, post_id, base_revision_id, optimization_type, skill_version_id, input_hash)` while Job active.
- `(user_id, post_id, created_at desc)`.

### PostAICandidate (`post_ai_candidates`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id/post_id` | UUID | Owner and target |
| `ai_run_id` | UUID | Unique run result |
| `base_revision_id` | UUID | Same as run |
| `candidate_revision_id` | UUID | AI snapshot |
| `status` | string | `pending/merge_required/applied/rejected/copied` |
| `field_diff_json` | JSONB | Safe summary and paths, not rendered HTML |
| `validation_json` | JSONB | Field validity, warnings and protected-token results |
| `applied_revision_id` | UUID? | New confirmation revision when applied |
| `created_at/reviewed_at` | timestamptz | Lifecycle timestamps |

### PostCandidateDecision (`post_candidate_decisions`)

Append-only review record.

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id/post_id/candidate_id` | UUID | Ownership chain |
| `action` | string | `apply_all/apply_body/apply_metadata/apply_fields/keep_current/reject/copy` |
| `selected_fields_json` | JSONB | Allowed field paths only |
| `rejected_fields_json` | JSONB | Optional explicit rejects |
| `current_revision_before_id` | UUID | Compare/apply basis |
| `result_revision_id` | UUID? | Set for apply/copy |
| `created_at` | timestamptz | Append-only |

## Settings and Derived Entities

### BlogSettings (`blog_settings`)

| Field | Type | Rules |
|---|---|---|
| `user_id` | UUID | PK/FK User |
| `schema_version` | string | `blog-settings.v1` |
| `create_defaults_json` | JSONB | Class/type/category/tag/status/editor/AI/Skill/model/language/generation flags |
| `clipboard_json` | JSONB | Cleanup, raw retention, URL detection, AI and Skill |
| `url_capture_json` | JSONB | Raw/snapshot/image extraction, default use, AI and Skill |
| `ai_apply_json` | JSONB | Auto-apply enabled and field policies; safety ceiling enforced |
| `word_cloud_json` | JSONB | Stop words, min frequency, max terms, excluded types |
| `version` | integer | Optimistic lock |
| `created_at/updated_at` | timestamptz | Audit timestamps |

Settings may reference owned IDs, but historical tasks store frozen resolved values.

### PostWordCloudSnapshot (`post_word_cloud_snapshots`)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | Owner |
| `source_kind` | string | `tag/keyword` |
| `filter_json` | JSONB | Normalized year/class/category/range filters |
| `filter_hash` | string | Index key |
| `terms_json` | JSONB | Bounded `{term,id,count}` list |
| `article_count` | integer | Included article count |
| `status` | string | `ready/stale/failed` |
| `async_job_id` | UUID? | Latest rebuild |
| `generated_at` | timestamptz | Last success |
| `error_code` | string? | Last rebuild error without removing result |

**Unique**: `(user_id, source_kind, filter_hash)`.

## Existing Relationship Reuse

- `PostTag`: unchanged join identity; service adds ownership and disabled-tag checks.
- `EntityRelation`: continues to link tasks/captures to Posts and can link merged sources; `PostSource` remains the authoritative raw capture record.
- `SearchDocument`: no schema change required initially; Post refresh now supplies summary, Markdown, category, tags, keywords, source URL and flattened structured data.
- `AsyncJob`/`AsyncJobEvent`: no new global statuses. Blog API derives display states from status, `current_step`, `PostAIRun.outcome`, and candidate status.
- `ActivityLog`: records source saved/extracted, revisions, Skill/default changes, candidate review, restore, taxonomy merge, settings and archive actions.

## State Transitions

### Post content status

| From | Event | To | Guard |
|---|---|---|---|
| new | blank/clipboard saved | `draft` or `triage` | Post + source + first revision committed |
| new | URL saved | `pending_parse` | URL source committed |
| `pending_parse` | extraction begins | `pending_parse` | Job processing shown separately |
| `pending_parse` | success | `draft` or `triage` | Extracted source and revision saved |
| `pending_parse` | partial/failure | `triage` | Original URL retained |
| `triage` | user edits/accepts | `draft` | Current revision created |
| `draft/triage/completed` | AI submitted | `ai_queued` or existing status + AI badge | Product projection may preserve completed state |
| AI active | worker begins | `ai_processing` or existing status + badge | Job ownership matches |
| AI done, unchanged | needs review | `ai_review` | Candidate valid |
| AI done, changed | conflict detected | `merge_required` | Current revision differs from base |
| review/merge | selected fields applied | `draft` or `completed` | Rechecked current version |
| any editable | user marks complete | `completed` | No requirement to publish |
| `completed/draft/triage` | archive | `archived` | Explicit user action |
| `archived` | restore | `draft` or prior stored state | New revision/activity if content restored |
| non-published internal | discard | `discarded` | Existing public deletion rules still apply |

Implementation may keep stable article `content_status` during a new optimization and expose `ai_display_status` separately; API must not make an already completed article appear unfinished merely because a re-optimization failed.

### PostSource status

`saved → pending → processing → completed|partial|failed|cancelled`; retry from `partial|failed` creates a new AsyncJob and returns source to `pending` while retaining previous error/attempt history in Job events.

### Candidate status

`pending → applied|rejected|copied`; `pending → merge_required` when current revision differs; `merge_required → applied|rejected|copied`. A terminal candidate is never reopened; regenerate creates a new run and candidate.

### Skill version

Versions have no mutable lifecycle. Skill `enabled` gates new matches only. Restore copies an old config into `version_number + 1` and changes `current_version_id`.

## Validation Rules

### Ownership

- Every PostSource, Revision, ContentType, Skill, SkillVersion, Run, Candidate, Decision, Keyword, taxonomy profile/default and snapshot lookup begins with `user_id`.
- Cross-row relationships must match user ownership; UUID existence is never enough.
- Protected snapshot access resolves PostSource ownership before issuing content or a short-lived URL.

### Field paths

- Candidate-selected fields use an allow-list: named top-level fields plus `structured_data.<defined-key>`.
- System/source paths, IDs, versions, timestamps, public status, raw source, task binding and Skill binding cannot be selected.
- Unknown JSON keys are rejected for new AI output but preserved in historical Post snapshots.

### Protected content

- Extract and hash fenced code, inline code, likely shell commands, URLs, numeric tokens, ISO/local dates and Markdown quotes before model call.
- Validation classifies `unchanged`, `changed_requires_confirmation`, `missing`, and `new_unverified`.
- Any protected change disables automatic application for the containing field.

### Size limits

- Current Markdown and each revision: 200,000 characters MVP.
- Clipboard raw text/HTML: configurable bounded maximum, initial 2 MiB equivalent.
- URL response: stream-limited initial 5 MiB compressed/decompressed safe policy; snapshot optional.
- Skill config: 256 KiB; field definition count and prompt sections bounded.
- Candidate output: same body limit plus bounded tags/keywords/structured fields.
- Messages contain identifiers only; no article body, raw HTML or Skill config.

## Migration and Backfill

1. Add nullable new Post columns and expanded PostRevision columns/checks.
2. Create new tables and indexes.
3. Seed per-user content types and a safe global default Skill only when the user has no blog configuration.
4. For every existing Post:
   - `content_status = completed` only if explicitly mapped by existing data is inappropriate; default to `draft`.
   - `content_class = essay`, `language = user.locale`, `structured_data_json = {}`.
   - Populate the current PostRevision `snapshot_json`; if missing, create a compatibility revision from current title/Markdown.
5. Set `current_revision_id` non-null after verification.
6. Add FK from `posts.category_id` to categories only after invalid legacy values are nulled and audited.
7. Expand revision source check without dropping rows.
8. Preserve publication status, slug, published timestamp and public endpoints unchanged.

**Rollback**:

- Before destructive downgrade, export references to new revisions and sources; downgrade cannot represent field-level snapshots in the old schema.
- Schema downgrade may drop new support tables only in non-production/test environments; operational rollback uses application rollback while retaining additive tables.

## Deletion and Retention

- Soft-deleting a Post hides it from private lists/search and prevents new jobs; running jobs check deletion before saving candidate.
- Raw source snapshots follow existing private asset retention. Deleting a snapshot does not delete PostSource metadata or normalized text unless the user deletes the article under总站策略.
- Skill versions and AI run references remain while referenced by revisions/tasks, even if the Skill identity is soft-deleted.
- Word-cloud snapshots and SearchDocuments are derived and may be deleted/rebuilt.
- Activity records retain IDs and safe summaries, never full article content.
