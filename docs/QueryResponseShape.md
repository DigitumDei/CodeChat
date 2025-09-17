# Query Response Shape

`POST /query` returns the text produced by the provider as a plain string.

```json
"Hello from CodeChat"
```

If the underlying provider result is missing the `text` field, the server returns an error envelope:

```json
{
  "error": {
    "code": "INVALID_PROVIDER_RESPONSE",
    "msg": "Provider response missing 'text' field"
  }
}
```
