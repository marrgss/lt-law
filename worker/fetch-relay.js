// Read-only relay to the TAR open data on data.gov.lt (D-019).
// data.gov.lt answers every request from GitHub's runners with HTTP 500 (D-018), but answers
// Cloudflare normally, so the nightly job fetches through this Worker. It forwards only GET
// requests for two datasets of the Seimas Chancellery, the acts (TAR) and the Seimas votes (D-054), only with the
// shared key, and passes the answer through unchanged.
const UPSTREAM = "https://get.data.gov.lt";
const PREFIXES = ["/datasets/gov/lrsk/teises_aktai/", "/datasets/gov/lrsk/balsavimai/"];
const UA = "lt-law/0.1 (open civic project; read-only; https://atviri-teises-aktai.lt)";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!env.RELAY_KEY || request.headers.get("x-relay-key") !== env.RELAY_KEY) {
      return new Response("forbidden\n", { status: 403 });
    }
    if (request.method !== "GET" || !PREFIXES.some((p) => url.pathname.startsWith(p)) || url.pathname.includes("..")) {
      return new Response("only GET " + PREFIXES.join("* or ") + "*\n", { status: 400 });
    }
    const r = await fetch(UPSTREAM + url.pathname + url.search, {
      headers: { "User-Agent": UA, Accept: "application/json" },
    });
    return new Response(r.body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") || "application/json" },
    });
  },

  // A punctual start for the nightly build (GitHub's own schedule ran 2-5 hours late, E1). Does nothing
  // without GH_DISPATCH_TOKEN (a fine-grained token: this repository, Actions: write only).
  async scheduled(event, env) {
    if (!env.GH_DISPATCH_TOKEN) return;
    const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/nightly.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "lt-law-fetch-relay",
      },
      body: JSON.stringify({ ref: "main", inputs: { scheduled: "true" } }),
    });
    console.log("dispatch nightly:", r.status);
  },
};
