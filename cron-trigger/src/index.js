const REPO = "gunjanmishra94/transit-mesh";

// Maps each Cloudflare Cron Trigger (wrangler.toml) to the GitHub Actions
// repository_dispatch event_type it should fire, which .github/workflows/
// rt-ingestion.yml and static-gtfs.yml listen for.
const CRON_TO_EVENT_TYPE = {
  "*/5 * * * *": "realtime-ingestion",
  "17 3 * * *": "static-gtfs-refresh",
};

export default {
  async scheduled(event, env, ctx) {
    const eventType = CRON_TO_EVENT_TYPE[event.cron];
    if (!eventType) {
      throw new Error(`no repository_dispatch mapping for cron "${event.cron}"`);
    }

    const response = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
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
  },
};
