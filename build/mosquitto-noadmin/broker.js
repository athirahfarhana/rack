/**
 * A drop-in replacement for `mosquitto -c mosquitto.conf -v` for machines
 * where the Mosquitto Windows installer is blocked by IT policy (needs
 * admin rights). This does the same job - a local MQTT broker on
 * localhost:1883 - but as a plain Node process, so it only needs whatever
 * rights `npm install` already has (same as running the frontend).
 *
 * Usage:
 *   npm install
 *   npm start
 *
 * Then point the backend at it exactly like Mosquitto - it's already the
 * default in backend/.env.example (MQTT_HOST=localhost, MQTT_PORT=1883).
 */
const aedes = require("aedes")();
const net = require("net");

const PORT = process.env.PORT || 1883;
const server = net.createServer(aedes.handle);

server.listen(PORT, () => {
  console.log(`Local MQTT broker (no-admin) listening on port ${PORT}`);
  console.log("Point backend/.env at MQTT_HOST=localhost MQTT_PORT=1883 (already the default).");
  console.log("Leave this window open - this is your broker for as long as you're developing.\n");
});

aedes.on("client", (client) => {
  console.log(`[connect]    ${client.id}`);
});

aedes.on("clientDisconnect", (client) => {
  console.log(`[disconnect] ${client.id}`);
});

aedes.on("publish", (packet, client) => {
  if (!client) return; // skip the broker's own internal messages
  const payload = packet.payload.toString();
  const shown = payload.length > 200 ? payload.slice(0, 200) + "…" : payload;
  console.log(`[publish]    ${packet.topic}  ${shown}`);
});

aedes.on("subscribe", (subscriptions, client) => {
  if (!client) return;
  console.log(`[subscribe]  ${client.id} -> ${subscriptions.map((s) => s.topic).join(", ")}`);
});

process.on("SIGINT", () => {
  console.log("\nShutting down broker...");
  server.close(() => process.exit(0));
});
