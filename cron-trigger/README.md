# cron-trigger

A Cloudflare Worker that replaces GitHub Actions' native `schedule:` trigger
for this repo's pipeline workflows.

## Why this exists

GitHub's `schedule:` event is queued and evaluated on GitHub's own infra,
and is documented to be delayed or dropped under platform load — worse the
higher the frequency. On this repo, `rt-ingestion.yml`'s `*/5 * * * *`
schedule was observed firing hours apart instead of every 5 minutes, and
`static-gtfs.yml`'s daily `17 3 * * *` schedule ran over 5 hours late.

Cloudflare Cron Triggers fire reliably. This Worker turns a single 5-minute
heartbeat — the finest interval Cloudflare supports — into `repository_dispatch`
POSTs to GitHub's API, which Actions treats as an immediate external event,
not a queued schedule evaluation. The workflows' native `schedule:` blocks
are kept as coarse fallbacks (hourly / same-day) in case this Worker itself
goes down — see the `on:` block comments in `../.github/workflows/rt-ingestion.yml`
and `static-gtfs.yml`.

Which jobs exist, whether each is enabled, and how often it actually fires
(every tick, every 30 min, daily, ...) live in the `CRON_STATE` KV
namespace, not in this Worker's code — see `src/index.js`. That state is
managed by [cron-orchestrator](https://github.com/gunjanmishra94/cron-orchestrator),
a separate app (React + Cloudflare Pages Functions) that reads/writes the
same KV namespace, so toggling a job or changing its frequency takes effect
on the next tick with no redeploy of this Worker.

## One-time setup

1. **Create a classic GitHub PAT** with the `public_repo` scope:
   [github.com/settings/tokens/new](https://github.com/settings/tokens/new)
   - Scope: **`public_repo`** only (not the full `repo` scope — this repo is
     public, so `public_repo` is enough and doesn't grant access to private
     repos)
   - **Must be classic, not fine-grained.** Fine-grained PATs return a 403
     ("Resource not accessible by personal access token") on
     `repository_dispatch` for public repositories no matter what
     permissions they're given — confirmed by hitting exactly that error
     here. GitHub's docs note fine-grained tokens aren't supported for this
     endpoint on public repos; classic `public_repo` is the only token type
     that actually works.
   - No expiration shorter than you're willing to come back and rotate this

2. **Authenticate wrangler** against your Cloudflare account:
   ```bash
   cd cron-trigger
   npx wrangler login
   ```

3. **Store the PAT as a Worker secret** (never put it in `wrangler.toml`):
   ```bash
   npx wrangler secret put GITHUB_DISPATCH_TOKEN
   # paste the PAT when prompted
   ```

4. **Deploy:**
   ```bash
   npx wrangler deploy
   ```

The Worker never serves HTTP traffic — it only runs on its one Cron Trigger
(`wrangler.toml`) plus the `CRON_STATE` KV binding. Seed that KV namespace
with the job list once (see cron-orchestrator's README for the shape), or
manage jobs entirely through that app once it's deployed.

## Verifying it's working

```bash
npx wrangler tail
```

Leave that running past a 5-minute boundary and watch for a dispatch call,
or check the Actions tab for `repository_dispatch`-triggered runs:

```bash
gh run list --workflow=rt-ingestion.yml --json event,createdAt,conclusion \
  -q '.[] | select(.event == "repository_dispatch")'
```

## Rotating the PAT

Classic PATs expire on whatever schedule you set at creation. When it does,
the Worker's dispatch calls start failing with a 401 (visible via
`wrangler tail` or Cloudflare's dashboard logs), and the workflows silently
fall back to their hourly/daily native schedule until you repeat steps 1
and 3 above with a fresh token.
