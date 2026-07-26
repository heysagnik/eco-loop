export async function fetchHistory(limit = 100) {
  const res = await fetch(`/state/history?limit=${limit}`);
  return res.json();
}

export async function fetchSummary() {
  const res = await fetch("/state/summary");
  return res.json();
}

export async function fetchMode() {
  const res = await fetch("/control/mode");
  return res.json();
}

export async function revertToBaseline() {
  const res = await fetch("/control/revert-to-baseline", { method: "POST" });
  return res.json();
}

export async function resumeAi() {
  const res = await fetch("/control/resume-ai", { method: "POST" });
  return res.json();
}

export async function startBenchmark() {
  const res = await fetch("/benchmark/start", { method: "POST" });
  return res.json();
}

export async function resetBenchmark() {
  const res = await fetch("/benchmark/reset", { method: "POST" });
  return res.json();
}

export async function fetchUpdates(since = 0) {
  const res = await fetch(`/state/updates?since=${since}`);
  return res.json();
}

const ERROR_RETRY_DELAY_MS = 2000;

export function startPolling(onData) {
  let stopped = false;
  let sinceVersion = 0;

  async function loop() {
    while (!stopped) {
      try {
        const payload = await fetchUpdates(sinceVersion);
        sinceVersion = payload.version ?? sinceVersion;
        onData({
          history: payload.history || [],
          summary: payload.summary || {},
          mode: payload.mode || "ai",
          liveTurn: payload.live_turn || { sim_time_hours: null, calls: [] },
        });
      } catch (e) {
        console.warn("Long-poll request failed:", e);
        await new Promise((resolve) => setTimeout(resolve, ERROR_RETRY_DELAY_MS));
      }
    }
  }

  loop();

  return {
    stop: () => {
      stopped = true;
    },
  };
}
