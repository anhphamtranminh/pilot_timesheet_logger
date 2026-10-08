# Inbox Triage Workflow

**Goal:** Help the user catch up by converting a raw inbox into a "Needs reply" + "Worth a look" digest.

**References:** `openapi.yaml` in this bundle is the source of truth for every call below. This guide names operations by `operationId` (with their tag) so it stays correct when paths or params change — look each one up in the spec for the current path, parameters, and response shape. Operations used: `listInbox` (tag: inbox), `batchGetUsers` (tag: users), `listSidebarSections` (tag: sidebar), `getThreadReplies` (tag: threads), `listMessages` (tag: messages).

---

## Core Principle

**Group conversations, not items.** Raw inbox is noisy. Grouping by thread or channel reveals signal. Then classify which conversations need a reply vs are FYI-only.

---

## Workflow Pattern

### 1. Scan Inbox

Call `listInbox` operation (see openapi.yaml, tag: inbox) to fetch recent inbox items. **Check the spec for current parameters** (e.g., `source`, `limit`, `before` cursor).

**Amount is flexible:**
- "What did I miss today?" → scan last 24 hours
- "Catch me up" → scan last 3–7 days
- "Triage inbox" → scan until you have enough signal (50+ conversations is usually plenty)

Stop when you have enough signal, not at an arbitrary count.

**Key principle:** Use the `source` parameter (or equivalent) to filter out bots before grouping.

---

### 2. Enrich: Resolve Names & Channels

- **Users:** Collect distinct `sender_id` values, then call `batchGetUsers` operation (see openapi.yaml, tag: users) to resolve display names.
- **Channels:** Call `listSidebarSections` operation (see openapi.yaml, tag: sidebar) to build `slug_by_channel_id` map.

This lets you render readable conversation summaries with links.

---

### 3. Group into Conversations

**Group key:** `thread_id` (if non-null) else `channel_id`. One group = one thread or one channel.

For each group collect:
- `key` — the group identifier (thread_id or channel_id)
- `is_thread` — boolean
- `count` — items in the group
- `participants` — participant names (exclude the user themselves)
- `kind` — see below
- `latest_item` — most recent item
- `recent` — last 2–3 items as "name: text" (capped 150 chars)

**Kind detection** — pick the strongest directed type present in the group:
```
mention / channel_mention in group  →  kind = "mention"
else if dm / dm_thread_reply        →  kind = "dm"
else if thread_reply (no dm/mention) → kind = "thread"
else                                 → kind = "channel"
```

See `InboxItem.type` enum in openapi.yaml for all types. Drop all-bot groups.

---

### 4. Rank & Decide What to Show

Sort by recency. **Show conversations that answer the user's question:**
- "What did I miss?" → ~10–15 conversations
- "Triage inbox" → ~20–30 conversations

Stop when you've covered their need. Note if you truncated (more conversations exist).

---

### 5. Check Unanswered (Directed Only)

**Only for kind ∈ {mention, dm, thread}.** Channel is never "unanswered" (channels are broadcast).

For each directed conversation:
1. Find the latest directed item (type ∈ mention, dm, thread_reply, dm_thread_reply, channel_mention)
2. Query recent replies (see openapi.yaml for exact parameters):
   - If `is_thread`: call `getThreadReplies` operation (tag: threads)
   - Else: call `listMessages` operation (tag: messages)
3. **Unanswered = true** if the user hasn't replied yet (check for their `author_id` with `created_at > directed_item.created_at`); **false** if they have.

Lightweight check — you're asking "did they reply?" not "is it resolved?"

---

### 6. LLM Classify Priority

Spawn a sub-agent to classify each conversation. One conversation per line:

**Input (pipe-delimited):**
```
key|kind|participants|count|unanswered|recent
```

**Sub-agent job:** Emit one line per conversation:
```
key|priority|needs_reply|reason
```

**Criteria:**
- **priority:** urgent | normal | low
  - **urgent:** directed + time-sensitive or matches user's stated focus
  - **low:** ambient channel noise, reactions, FYI-only
  - **normal:** everything else
- **needs_reply:** true if `unanswered=true AND kind ∈ {dm, mention, thread}`; else false. (Channel is never needs_reply.)
- **reason:** short (≤8 words), no pipes

The LLM is your classifier — trust its judgment.

---

### 7. Render Digest

Two sections:

**You haven't replied to these** — unanswered=true conversations  
**Worth a look** — priority ∈ {urgent, normal} and unanswered=false

Omit low-priority ambient items (noise).

One line per conversation:
```
• {participants} ({kind}, {count}) — "{latest text, ~80 chars}"  [open]({permalink})
```

**Permalink construction** (see the Backlinks table in `SKILL.md` for all patterns):
- Specific message: `https://workspace.gradion.com/channels/{slug}/messages/{message_id}`
- Where `slug` comes from the sidebar lookup, `message_id` from the latest item

**Cap output at ~8–15 lines** (user reads it in one go). If truncated, add: _(more conversations not shown)_.

---

### 8. (Optional) Save Stats

If user asks, collect aggregate stats (no PII, no message content):
- Items scanned, conversations grouped, collapse ratio
- Distribution of notification types (see `InboxItem.type` enum)
- Unanswered count
- Priority distribution (urgent/normal/low)
- Conversation size statistics

Helps track inbox shape over time.

---

## Key Decisions (Why These Principles)

| Decision | Why |
|----------|-----|
| Group thread_id first, then channel_id | Threads are focused; channels are broadcast. Grouping reveals signal. |
| Filter bots before grouping | Bot spam inflates counts and dilutes the user's actual workload. |
| Kind = strongest directed type | Type is ground truth. Check openapi.yaml `InboxItem.type` enum. |
| Unanswered check: top-N only | Full scan is expensive. Top conversations matter most. |
| LLM classify priority | The LLM understands context. Let it decide urgent vs normal. |
| Channel never needs_reply | Channels are broadcast-first. User replies when they want to. |
| Cap output ~8–15 lines | User reads it in one sitting. More is overwhelming. |

---

## What NOT to Do

- **Don't fetch a fixed number of items.** Fetch until you have enough signal. 50 items grouped into 20 conversations beats 300 items grouped into 18.
- **Don't force top-30.** Show as many as the user's question demands.
- **Don't make up priorities.** Ask the LLM sub-agent. It's better at balancing context than hard rules.
- **Don't guess at type values.** Check `InboxItem.type` enum in openapi.yaml.
- **Don't hard-code endpoints.** Refer to openapi.yaml if unsure about parameter names, response shapes, or availability.

---

## Checklist (principles, not a script)

- [ ] Bootstrap as SKILL.md describes, then scan via `listInbox` — filter bots through the source filter param (see the spec) before grouping
- [ ] Scan until you have enough signal for the user's question, not a fixed count
- [ ] Enrich names and channels with `batchGetUsers` and `listSidebarSections`
- [ ] Group by `thread_id` (else `channel_id`); detect kind from the strongest directed type
- [ ] Rank by recency; show as many conversations as the question demands
- [ ] Check unanswered for directed conversations only, querying replies per kind (`getThreadReplies` vs `listMessages`)
- [ ] Let the LLM classify priority — criteria, not hard rules
- [ ] Render two sections (needs-reply + worth-a-look); link each conversation
- [ ] (Optional) Save aggregate stats if the user asks
