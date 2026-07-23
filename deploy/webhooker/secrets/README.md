# Deployment secrets

Create `review.env` and `production.env` on the host. They are deliberately not committed.

```dotenv
SECRET_KEY=<at-least-32-random-bytes>
```

Generate independent high-entropy values, for example with `openssl rand -hex 32`. Use different
values for review and production, create files with a restrictive umask, and keep both files mode
`0600`. Changing a key invalidates all sessions and bearer tokens in that environment.
