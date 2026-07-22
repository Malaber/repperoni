# Deployment secrets

Create `review.env` and `production.env` on the host. They are deliberately not committed.

```dotenv
SECRET_KEY=<at-least-32-random-bytes>
```

Use different values for review and production.
