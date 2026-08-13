# Data Model

No new persistent entities are required.

- **Current page session**: ephemeral client state that begins empty and receives an existing persistent conversation ID only after the user sends a message.
- **Article result card**: derived client view of an existing owned task result; contains article ID, title, optional category/tags and private detail link.
- **Historical conversation**: unchanged persistent entity; it remains owner-scoped but is not loaded on Agent page entry.
