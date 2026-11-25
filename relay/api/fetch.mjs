// Fetch relay for the timetable watcher: GitHub's runners cannot reach the
// Indian Railways sites, this function (pinned to Mumbai, bom1) can.
//
//   GET|HEAD /api/fetch?url=<https URL on a railway host>
//   X-Relay-Secret: <RELAY_SECRET>
//
// Only the hosts below, only GET and HEAD, only with the secret. The upstream
// status is returned as is; its headers are copied as x-upstream-<name> (Vercel
// may rewrite content-length on a HEAD). A relay-side failure carries
// x-relay-error instead, so the caller can tell it from a railway 404.
import { timingSafeEqual } from "node:crypto";

const HOSTS = new Set([
  "wr.indianrailways.gov.in",
  "oldwr.indianrailways.gov.in",
  "cr.indianrailways.gov.in",
  "oldcr.indianrailways.gov.in",
]);
const COPY = ["content-type", "content-length", "last-modified", "etag"];
const UA = "rahi-timetable-watch/1.0 (open-source Mumbai local timetable; github.com/faraazb/rahi)";
const MAX_REDIRECTS = 5;

function fail(status, why) {
  return new Response(why + "\n", { status, headers: { "x-relay-error": why, "cache-control": "no-store" } });
}

function authorised(request) {
  const want = process.env.RELAY_SECRET || "";
  const got = request.headers.get("x-relay-secret") || "";
  if (want.length < 32) return false; // fail closed if the secret is unset or weak
  const a = Buffer.from(want), b = Buffer.from(got);
  return a.length === b.length && timingSafeEqual(a, b);
}

function allowed(raw) {
  try {
    const u = new URL(raw);
    return u.protocol === "https:" && HOSTS.has(u.hostname) && !u.username && !u.password && !u.port ? u : null;
  } catch {
    return null;
  }
}

async function relay(request) {
  if (!authorised(request)) return fail(401, "unauthorised");
  let target = allowed(new URL(request.url).searchParams.get("url") || "");
  if (!target) return fail(400, "url must be https on a railway host");

  let r;
  for (let hop = 0; ; hop++) {
    try {
      r = await fetch(target, {
        method: request.method,
        headers: { "User-Agent": UA },
        redirect: "manual",
        signal: AbortSignal.timeout(50_000),
      });
    } catch (e) {
      return fail(502, `upstream: ${e.cause?.code || e.name || e}`);
    }
    const loc = r.headers.get("location");
    if (r.status < 300 || r.status >= 400 || !loc) break;
    if (hop >= MAX_REDIRECTS) return fail(502, "too many redirects");
    target = allowed(new URL(loc, target).href); // every hop stays on a railway host
    if (!target) return fail(502, "redirect off the railway hosts");
  }

  const headers = { "cache-control": "no-store", "x-relay-url": target.href };
  for (const k of COPY) {
    const v = r.headers.get(k);
    if (v != null) headers[`x-upstream-${k}`] = v;
  }
  if (r.headers.get("content-type")) headers["content-type"] = r.headers.get("content-type");
  return new Response(request.method === "HEAD" ? null : r.body, { status: r.status, headers });
}

export const GET = relay;
export const HEAD = relay;
