# Tendrl Python SDK

[![Version](https://img.shields.io/badge/version-0.1.6-blue.svg)](https://github.com/tendrl-inc-labs/contact-python)
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)
[![License](https://img.shields.io/badge/license-MIT%20%2B%20Commons%20Clause-blue.svg)](LICENSE)

A Python client for the Tendrl data collection platform. It queues your messages, sends them in batches sized to the machine's spare capacity, and can hold them on disk while the network is away.

## Installation

Install from GitHub. The SDK is not distributed through PyPI.

```bash
uv add git+https://github.com/tendrl-inc-labs/contact-python
```

```bash
pip install git+https://github.com/tendrl-inc-labs/contact-python
```

## Quick start

```python
from tendrl import Client

client = Client(api_key="your_key")   # or set TENDRL_KEY in the environment
client.start()

client.publish({"temperature": 23.5, "humidity": 65}, tags=["sensor"])

client.stop()
```

`publish()` puts the message on a queue and returns an empty string straight away. A background thread does the sending. That means a failed send cannot be reported through the return value, so the client reports it through the logging module instead. See [Knowing when delivery fails](#knowing-when-delivery-fails).

## Choosing the server

By default the client talks to `https://app.tendrl.com`. Point it somewhere else for local development or staging:

```python
client = Client(api_key="your_key", app_url="http://192.168.1.50:8000")
```

```bash
export TENDRL_APP_URL=http://192.168.1.50:8000
```

The explicit `app_url` argument wins, then `TENDRL_APP_URL`, then the production default. A bare origin gets `/api` appended, and a URL that already ends in `/api` is left alone, so both forms work.

## Collecting on a schedule

The `tether` decorator wraps a function so its return value is published each time you call it. It does not schedule anything; call it from your own loop.

```python
import time

@client.tether(tags=["metrics"])
def collect():
    return {"cpu": 42.0, "memory": 84.0}

while True:
    collect()
    time.sleep(60)
```

## Headless mode

Headless mode runs no background thread. Each `publish()` sends immediately and returns the server's reply, which suits short scripts and serverless functions.

```python
client = Client(api_key="your_key", headless=True)
response = client.publish({"event": "deploy"}, tags=["ci"])
```

There is no `start()` to call. `stop()` still closes the HTTP connection.

## Knowing when delivery fails

When a message cannot be delivered, the client logs a warning through the standard `logging` module under the logger name `tendrl`:

```
Tendrl: DROPPED 3 message(s) that could not be delivered to https://app.tendrl.com/api.
Set offline_storage=True to hold undelivered messages for retry instead of losing them.
```

You do not have to configure logging to see this. Python's last-resort handler puts warnings on stderr. To route it with the rest of your logs:

```python
import logging
logging.getLogger("tendrl").setLevel(logging.WARNING)
```

A client that cannot reach the server reports at most once a minute, with a count of what happened in between, so a long outage does not fill the log.

`debug=True` is a separate thing. It prints verbose diagnostics straight to stdout and is not routed through `logging`.

## Offline storage

With `offline_storage=True` a message that cannot be sent is written to a local SQLite file instead of being discarded, and re-sent when the connection returns. Only messages the server actually accepted are removed from the store.

```python
client = Client(
    api_key="your_key",
    offline_storage=True,
    db_path="tendrl_offline.db",
)
```

`db_path` may be absolute. The directory has to exist and be writable, or the constructor raises.

Stored messages expire after an hour. Without this option, a message that cannot be delivered is lost, and the warning above is your only sign of it.

## Receiving messages

Pass a callback to receive messages addressed to your entity. The client polls for them only when a callback is set.

```python
def on_message(message):
    print(message["data"])

client = Client(api_key="your_key", callback=on_message, check_msg_rate=5.0)
```

The callback receives the decoded message dictionary as the server sent it. An exception raised inside it is logged and does not stop the client.

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str` | `None` | API key. Falls back to the `TENDRL_KEY` environment variable |
| `app_url` | `str` | `None` | Server URL. Falls back to `TENDRL_APP_URL`, then `https://app.tendrl.com` |
| `headless` | `bool` | `False` | Send synchronously with no background thread |
| `debug` | `bool` | `False` | Print verbose diagnostics to stdout, separate from `logging` |
| `offline_storage` | `bool` | `False` | Hold undelivered messages on disk and retry them |
| `db_path` | `str` | `"tendrl_offline.db"` | Where to keep the offline store |
| `callback` | `Callable` | `None` | Handler for inbound messages. Setting it turns on polling |
| `check_msg_rate` | `float` | `3.0` | Seconds between inbound checks |
| `check_msg_limit` | `int` | `1` | Maximum messages fetched per check |
| `max_queue_size` | `int` | `1000` | Outbound queue capacity |
| `min_batch_size` | `int` | `10` | Smallest batch the sender will build |
| `max_batch_size` | `int` | `100` | Largest batch the sender will build |
| `min_batch_interval` | `float` | `0.1` | Shortest wait between batches, in seconds |
| `max_batch_interval` | `float` | `1.0` | Longest wait between batches, in seconds |
| `target_cpu_percent` | `float` | `65.0` | CPU level the batch sizer aims to stay under |
| `target_mem_percent` | `float` | `75.0` | Memory level the batch sizer aims to stay under |
| `mode` | `str` | `"api"` | Transport. Only `"api"` is supported in this release |

Batch size is recalculated on every pass from current CPU, memory and queue depth, between `min_batch_size` and `max_batch_size`.

## API

### `publish(msg, tags=None, entity="", wait_response=False, timeout=5)`

Publishes a `dict` or `str`. Anything else raises `ValueError`.

Queued by default, returning `""` immediately. With `wait_response=True` it sends inline and returns the server's parsed JSON reply. Setting `entity` routes the message to another entity, and note that doing so drops `wait_response`.

### `tether(tags=None, write_offline=False, db_ttl=3600)`

Decorator that publishes a function's return value each time it is called. With `write_offline=True` and offline storage enabled, a message that finds the queue full is written to disk with the given time to live.

### `check_msg()`

Fetches pending inbound messages and hands each to the callback. Returns nothing, and does nothing at all if no callback is set. The client calls this for you on the `check_msg_rate` schedule.

### `start()` / `stop()`

`start()` launches the sender thread. `stop()` asks it to finish the batch in hand, then closes the HTTP connection and the offline store. Neither is needed in headless mode, though `stop()` still closes the connection.

### `check_connection_state()` / `process_offline_messages()`

`check_connection_state()` probes the server and returns a boolean. `process_offline_messages()` drains the offline store. The sender calls both on its own; they are exposed for callers who want to force the issue.

## Queue behavior

If the sender cannot keep up, `publish()` waits about a second for room, then hands the message to offline storage, or reports it as dropped when storage is off. It does not block your loop waiting for space.

## Requirements

Python 3.9 or newer. `httpx` and `psutil`.

## License

Copyright (c) Tendrl, Inc. 2025-2026. Licensed under the MIT License with Commons Clause and Client Use Restriction. See [LICENSE](LICENSE) for the terms.
