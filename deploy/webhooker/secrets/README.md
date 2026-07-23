# Deployment secrets

Create `review.env` and `production.env` on the host. They are deliberately not committed.

```dotenv
SECRET_KEY=<at-least-32-random-bytes>
```

Generate independent high-entropy values, for example with `openssl rand -hex 32`. Use different
values for review and production, create files with a restrictive umask, and keep both files mode
`0600`. Changing a key invalidates all sessions and bearer tokens in that environment.

Production registration is closed by default. For the first owner only, temporarily add these to
`production.env`, redeploy, and enter the token as the setup code:

```dotenv
REGISTRATION_MODE=first-user
REGISTRATION_BOOTSTRAP_TOKEN=<independent-at-least-32-random-bytes>
```

After the owner passkey is created, change `REGISTRATION_MODE=closed`, remove
`REGISTRATION_BOOTSTRAP_TOKEN`, and redeploy. The database uniqueness constraint also prevents a
second first-user registration if two valid requests race.
