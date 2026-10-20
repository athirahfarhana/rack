"""
Stand-in for real ESP32 gateway firmware, for testing the MQTT pipeline
before hardware/firmware is ready. Loops a heartbeat publish forever (like
a real gateway's main loop would), and announces one fake zone module via
discovery on startup so it also shows up as an "Unassigned Device".

Usage:
    python simulate_gateway.py
    python simulate_gateway.py --gw-id GW-TEST-02 --interval 30

Stop with Ctrl+C.
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt

DEFAULT_HOST = "broker.hivemq.com"
DEFAULT_PORT = 1883
DEFAULT_PREFIX = "warehouse/racks"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gw-id", default="GW-TEST-01", help="Gateway ID to simulate")
    parser.add_argument("--node-uuid", default="DE:AD:BE:EF:00:01", help="Fake zone module MAC to announce")
    parser.add_argument("--host", default=DEFAULT_HOST, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="MQTT topic prefix")
    parser.add_argument("--interval", type=int, default=20, help="Seconds between heartbeats (real hardware: 60)")
    args = parser.parse_args()

    base = f"{args.prefix}/{args.gw_id}"
    client = mqtt.Client(client_id=f"sim-{args.gw_id}")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    # One-time discovery, so a Zone Module shows up in "Unassigned Devices" too.
    client.publish(
        f"{base}/tx/discovery",
        json.dumps(
            {
                "event": "node_discovered",
                "gateway_id": args.gw_id,
                "node_uuid": args.node_uuid,
                "hardware_rev": "1.0",
                "capabilities": ["led_rgb"],
            }
        ),
    )
    print(f"Announced fake zone module {args.node_uuid} on gateway {args.gw_id}")

    uptime = 0
    print(f"Publishing heartbeat for {args.gw_id} to {args.host}:{args.port} every {args.interval}s. Ctrl+C to stop.")
    try:
        while True:
            client.publish(
                f"{base}/tx/heartbeat",
                json.dumps(
                    {
                        "event": "heartbeat",
                        "gateway_id": args.gw_id,
                        "status": "online",
                        "active_nodes_count": 1,
                        "wifi_rssi": -45,
                        "uptime_seconds": uptime,
                    }
                ),
            )
            print(f"[{uptime}s] heartbeat sent")
            uptime += args.interval
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
