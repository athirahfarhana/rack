// Thin REST client for the Smart Warehouse backend. In dev, Vite proxies
// /api -> the FastAPI backend (see vite.config.js); in prod (nginx), the
// same relative path is proxied server-side (see nginx.conf).

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getLayout: () => request("/api/layout"),
  saveLayout: (layout) => request("/api/layout", { method: "POST", body: JSON.stringify(layout) }),

  getDevices: () => request("/api/zone-modules"),
  addZoneModule: (payload) => request("/api/zone-modules", { method: "POST", body: JSON.stringify(payload) }),
  deleteZoneModule: (moduleId) => request(`/api/zone-modules/${encodeURIComponent(moduleId)}`, { method: "DELETE" }),
  assignZoneModule: (zoneId, zoneModuleId) =>
    request(`/api/zones/${encodeURIComponent(zoneId)}/assign`, {
      method: "POST",
      body: JSON.stringify({ zoneModuleId }),
    }),
  unassignZone: (zoneId) => request(`/api/zones/${encodeURIComponent(zoneId)}/unassign`, { method: "POST" }),
  updateZoneModule: (moduleId, patch) =>
    request(`/api/zone-modules/${encodeURIComponent(moduleId)}`, { method: "PATCH", body: JSON.stringify(patch) }),

  getGateways: () => request("/api/gateways"),
  addGateway: (gwId, rackId) =>
    request("/api/gateways", { method: "POST", body: JSON.stringify({ gwId, rackId }) }),
  deleteGateway: (gatewayId) => request(`/api/gateways/${encodeURIComponent(gatewayId)}`, { method: "DELETE" }),
  pingGateway: (gwId) => request(`/api/gateways/${encodeURIComponent(gwId)}/ping`, { method: "POST" }),
  getPayloadLog: (gwId) => request(`/api/gateways/${encodeURIComponent(gwId)}/payload-log`),
  identifyModule: (moduleId) => request(`/api/zone-modules/${encodeURIComponent(moduleId)}/identify`, { method: "POST" }),
  getJobsRecent: (limit = 20) => request(`/api/boxes/jobs/recent?limit=${limit}`),

  getWorkers: () => request("/api/workers"),
  getSystemConfig: () => request("/api/system/config"),

  inboundStore: (boxId, zoneId) =>
    request("/api/boxes/inbound", { method: "POST", body: JSON.stringify({ boxId, zoneId }) }),
  buildPickList: (boxIds) => request("/api/boxes/pick-list", { method: "POST", body: JSON.stringify({ boxIds }) }),
  confirmPick: (boxId) => request("/api/boxes/pick/confirm", { method: "POST", body: JSON.stringify({ boxId }) }),

  getStats: () => request("/api/dashboard/stats"),
  getRecentEvents: (limit = 40) => request(`/api/events/recent?limit=${limit}`),
  getHealth: () => request("/api/health"),
  getMode: () => request("/api/mode"),
  setMode: (mode) => request("/api/mode", { method: "POST", body: JSON.stringify({ mode }) }),

  getZoneOccupancy: () => request("/api/zones/occupancy"),
  getBox: (boxId) => request(`/api/boxes/${encodeURIComponent(boxId)}`),

  sendChat: (message, sessionId) =>
    request("/api/chat", { method: "POST", body: JSON.stringify({ message, sessionId }) }),
};

/** Opens the live event WebSocket with automatic reconnect + polling
 * fallback signalled via the onStatusChange callback. */
export function connectLiveEvents(onEvent, onStatusChange) {
  let socket = null;
  let closedByCaller = false;
  let retryDelay = 1000;

  function connect() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${window.location.host}/ws/events`);

    socket.onopen = () => {
      retryDelay = 1000;
      onStatusChange?.(true);
    };
    socket.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data));
      } catch {
        /* ignore malformed frame */
      }
    };
    socket.onclose = () => {
      onStatusChange?.(false);
      if (!closedByCaller) {
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 15000);
      }
    };
    socket.onerror = () => socket?.close();
  }

  connect();
  return () => {
    closedByCaller = true;
    socket?.close();
  };
}
