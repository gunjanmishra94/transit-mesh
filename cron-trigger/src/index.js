// Fires every 1 minute (wrangler.toml). Every other cadence (5 min,
// hourly, daily, ...) is simulated by checking, per job, whether enough
// time has passed since it last fired — so the cron-orchestrator app can
// change a job's intervalMinutes or enabled flag in KV and have it take
// effect on the very next tick, no redeploy of this Worker required.
//
// Job shape (KV key "jobs", a JSON array — see cron-orchestrator's
// functions/api/jobs.ts for the source of truth on this shape):
//   { id, name, repo, eventType, enabled, intervalMinutes, lastTriggeredAt }
//
// A job with intervalMinutes: 1 fires on every tick, the fastest this
// Worker can go. A job with a heavy per-run cost (e.g. a dbt build) set
// this low can pile up a queue in GitHub Actions if runs take longer than
// the interval, since the workflows' motherduck-writer concurrency group
// queues overlapping runs rather than dropping them.

// Ticks can land a second or two early/late; without slack, a job whose
// last run was, say, 59.5s ago (instead of a clean 60s) would be skipped
// for a full extra interval instead of firing this tick.
const DUE_SLACK_MS = 5_000;

async function dispatch(repo, eventType, token) {
  const response = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "transit-mesh-cron-trigger",
    },
    body: JSON.stringify({ event_type: eventType }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`dispatch of "${eventType}" failed: ${response.status} ${body}`);
  }
}

export default {
  async scheduled(_event, env, _ctx) {
    const raw = await env.CRON_STATE.get("jobs");
    const jobs = raw ? JSON.parse(raw) : [];
    if (jobs.length === 0) return;

    const now = Date.now();
    let changed = false;
    const errors = [];

    for (const job of jobs) {
      if (!job.enabled) continue;

      const last = job.lastTriggeredAt ? new Date(job.lastTriggeredAt).getTime() : 0;
      const dueAt = last + job.intervalMinutes * 60_000 - DUE_SLACK_MS;
      if (now < dueAt) continue;

      try {
        await dispatch(job.repo, job.eventType, env.GITHUB_DISPATCH_TOKEN);
        job.lastTriggeredAt = new Date(now).toISOString();
        changed = true;
      } catch (err) {
        errors.push(err.message);
      }
    }

    if (changed) {
      await env.CRON_STATE.put("jobs", JSON.stringify(jobs));
    }

    if (errors.length > 0) {
      throw new Error(errors.join("; "));
    }
  },
};
