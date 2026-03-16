# web_fetch

Fetch the content of a URL and return it as text. If the manifest defines a non-empty `allowlist`, only URLs matching one of the listed prefixes are permitted — all others are rejected.

The Operator controls which URLs are reachable by editing the `allowlist` field in the manifest via `evolution_proposal`.

## Examples

```
→ web_fetch({ "url": "https://example.com/feed.xml" })
```

## Parameters

- `url` (required) — URL to fetch. Must match an allowlisted prefix if `allowlist` is non-empty.
