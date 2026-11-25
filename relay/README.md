# relay

The Indian Railways sites do not answer GitHub's runners (the requests time out), so the
timetable watcher fetches through this Vercel function, pinned to Mumbai (`bom1`).

    GET|HEAD https://rahi-relay.vercel.app/api/fetch?url=<https URL>
    X-Relay-Secret: <RELAY_SECRET>

- Only `wr.`, `oldwr.`, `cr.` and `oldcr.indianrailways.gov.in`, over https, GET or HEAD.
  Redirects are followed only while they stay on those hosts.
- Without the right secret it answers 401; with no secret configured it refuses everything.
- The railway's status code is passed through; its headers come back as
  `x-upstream-<name>`. Errors of the relay itself carry `x-relay-error`.

## Secrets

| Where | Name | Value |
|---|---|---|
| Vercel project `rahi-relay`, Production | `RELAY_SECRET` (sensitive) | 64 hex characters |
| GitHub repository secret | `WATCH_RELAY_SECRET` | the same value |
| GitHub repository variable | `WATCH_RELAY_URL` | `https://rahi-relay.vercel.app/api/fetch` |

`watch/watch.py` uses the relay when `WATCH_RELAY_URL` is set and fetches directly otherwise.

## Deploy / rotate the secret

```sh
cd relay
vercel deploy --prod
# rotate: one new value in both places, then redeploy so the function reads it
s=$(openssl rand -hex 32)
vercel env rm RELAY_SECRET production --yes
printf %s "$s" | vercel env add RELAY_SECRET production --sensitive
printf %s "$s" | gh secret set WATCH_RELAY_SECRET
vercel deploy --prod
```

Usage is about 25 requests a day, well inside Vercel's Hobby limits.
