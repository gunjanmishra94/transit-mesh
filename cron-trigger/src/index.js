// Fires every 5 minutes (wrangler.toml), the finest interval Cloudflare
// Cron Triggers support. Every other cadence (10 min, hourly, daily, ...)
// is simulated by checking, per job, whether enough time has passed since
// it last fired — so the cron-orchestrator app can change a job's
// intervalMinutes or enabled flag in KV and have it take effect on the
// very next tick, no redeploy of this Worker required.
//
// Job shape (KV key "jobs", a JSON array — see cron-orchestrator's
// functions/api/jobs.ts for the source of truth on this shape):
//   { id, name, repo, eventType, enabled, intervalMinutes, lastTriggeredAt }
//
// intervalMinutes should be a multiple of 5; a smaller value just means
// "fire on every tick" since this Worker only ticks every 5 minutes.

// Ticks can land a few seconds early/late; without slack, a job whose
// last run was (say) exactly 4m58s ago would be skipped for a full extra
// interval instead of firing this tick.
const DUE_SLACK_MS = 30_000;

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
