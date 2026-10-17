"""Push JSON "custom app" / notify frames to an AWTRIX 3 pixel matrix over HTTP or MQTT."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

try:
    import paho.mqtt.client as mqtt
except ImportError:  # MQTT is optional; HTTP mode doesn't need it.
    mqtt = None


@dataclass
class AwtrixConfig:
    transport: str = "http"  # "http" or "mqtt"
    host: str = "192.168.1.50"
    http_timeout: float = 2.0

    mqtt_broker: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_password: str | None = None
    mqtt_prefix: str = "awtrix_xxxx"  # device name as set in the AWTRIX MQTT settings

    @classmethod
    def from_env(cls) -> "AwtrixConfig":
        return cls(
            transport=os.environ.get("AWTRIX_TRANSPORT", "http").lower(),
            host=os.environ.get("AWTRIX_HOST", "192.168.1.50"),
            http_timeout=float(os.environ.get("AWTRIX_HTTP_TIMEOUT", "2.0")),
            mqtt_broker=os.environ.get("AWTRIX_MQTT_BROKER", "127.0.0.1"),
            mqtt_port=int(os.environ.get("AWTRIX_MQTT_PORT", "1883")),
            mqtt_user=os.environ.get("AWTRIX_MQTT_USER") or None,
            mqtt_password=os.environ.get("AWTRIX_MQTT_PASSWORD") or None,
            mqtt_prefix=os.environ.get("AWTRIX_MQTT_PREFIX", "awtrix_xxxx"),
        )


class AwtrixClient:
    """Thin wrapper around AWTRIX's /api/custom, /api/notify (HTTP) and <prefix>/custom/<app> (MQTT).

    Field names (text/color/icon/progress/...) match AWTRIX 3 as documented on the device's
    own /api help page at the time this was written. If your firmware reports different key
    names there, adjust the dict keys below to match — the transport logic stays the same.
    """

    def __init__(self, config: AwtrixConfig):
        self.config = config
        self._mqtt_client: "mqtt.Client | None" = None
        if config.transport == "mqtt":
            if mqtt is None:
                raise RuntimeError("paho-mqtt not installed; run: pip install paho-mqtt")
            self._mqtt_client = mqtt.Client()
            if config.mqtt_user:
                self._mqtt_client.username_pw_set(config.mqtt_user, config.mqtt_password)
            self._mqtt_client.connect(config.mqtt_broker, config.mqtt_port, keepalive=30)
            self._mqtt_client.loop_start()

    def push_custom_app(self, app_name: str, payload: dict[str, Any]) -> None:
        """Create/refresh a custom app frame. Empty payload ({}) removes it."""
        if self.config.transport == "http":
            url = f"http://{self.config.host}/api/custom"
            resp = requests.post(
                url,
                params={"name": app_name},
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=self.config.http_timeout,
            )
            resp.raise_for_status()
        else:
            assert self._mqtt_client is not None
            topic = f"{self.config.mqtt_prefix}/custom/{app_name}"
            self._mqtt_client.publish(topic, json.dumps(payload), qos=0, retain=True)

    def push_notify(self, payload: dict[str, Any]) -> None:
        """One-off full-screen notification (HTTP only; use a custom app over MQTT instead)."""
        if self.config.transport != "http":
            raise RuntimeError("notify() is only implemented over HTTP in this client")
        url = f"http://{self.config.host}/api/notify"
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self.config.http_timeout,
        )
        resp.raise_for_status()

    def clear_app(self, app_name: str) -> None:
        self.push_custom_app(app_name, {})

    def close(self) -> None:
        if self._mqtt_client is not None:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
