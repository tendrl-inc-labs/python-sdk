# Tendrl Python SDK

[![Version](https://img.shields.io/badge/version-0.1.6-blue.svg)](https://github.com/tendrl-inc/clients/nano_agent)
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

A Python SDK for the Tendrl data collection platform with cross-platform UNIX socket support, offline storage, and dynamic batching.

## Features

- 🔌 **Cross-Platform Communication**: Windows 10 1803+, Linux, macOS
- 🔄 **Dual Operating Modes**: HTTP API and Tendrl Nano Agent (Unix Socket)  
- 💾 **Offline Message Storage**: SQLite-based persistence with TTL
- ⚡ **Dynamic Batching**: CPU/memory-aware batch sizing
- 🎯 **Resource Monitoring**: Automatic system resource adaptation
- 🔐 **Secure Communication**: AF_UNIX sockets + HTTPS API
- 📊 **Performance Metrics**: Built-in system monitoring utilities

## Platform Support

### Windows

- **Requirements**: Windows 10 version 1803+ or Windows Server 2019+ (Agent Mode)
- **Recommended**: Use [Tendrl Nano Agent](`https://tendrl.com/docs/nano_agent/`) for optimal performance
- **Agent Installation**: Download and run `tendrl-agent.exe` with your API key
- **Connection**: Python SDK connects automatically to the local agent

### Unix/Linux/macOS

- **Native Support**: Works on all modern versions
- **Recommended**: Use [Tendrl Nano Agent](`https://tendrl.com/docs/nano_agent/`) for optimal performance
- **Direct API**: Can also connect directly to Tendrl API without local agent

## Operating Modes

The Python SDK supports two operating modes optimized for different use cases:

### 📡 Direct API Mode (Recommended for Simplicity)

**How it works**: Python SDK → HTTP/2 → Tendrl Server

```python
client = Client(mode="api", api_key="your_key")  # Direct to server
```

**Benefits:**

- **Simple setup**: No additional components required
- **Direct control**: Full visibility into HTTP requests and responses
- **Dynamic batching**: CPU/memory-aware batching (10-500 messages)
- **Offline storage**: SQLite persistence during network outages
- **Connection pooling**: httpx HTTP/2 connection reuse
- **Automatic retries**: Built-in retry mechanisms and error handling
- **Resource monitoring**: Adaptive behavior based on system load

**Performance Characteristics:**

- **Light Load** (< 10 msg/sec): ~2-5ms per message
- **Heavy Load** (100+ msg/sec): ~0.5-1ms per message (true HTTP batch requests)
- **Per-message latency**: ~2-10ms individual, ~0.5-1ms batched
- **Batching**: True HTTP batching - multiple messages per HTTP request
- **Resource usage**: Higher CPU/memory due to Python interpreted overhead

### 🚀 Nano Agent Mode (Recommended for Performance)

**How it works**: Python SDK → Unix Socket → Go Nano Agent → HTTP/2 → Tendrl Server

```python
client = Client(mode="agent")  # Connects to local Go agent
```

**Benefits:**

- **Superior performance**: 5-20x faster due to Go efficiency + Unix socket IPC
- **Single point of egress**: One agent serves multiple applications/languages on same host
- **Enhanced batching**: Go agent optimizes HTTP request batching better than Python
- **Shared efficiency**: Single Go process serves multiple Python applications
- **Centralized configuration**: Manage API keys and settings in one place
- **Optimized connection management**: Go's superior HTTP/2 implementation
- **Advanced resource adaptation**: More sophisticated CPU/memory monitoring
- **Production reliability**: Battle-tested Go networking stack
- **Lower system overhead**: Compiled efficiency vs Python interpreted overhead

**Performance Characteristics:**

- **Light Load** (< 10 msg/sec): ~0.5ms per message  
- **Heavy Load** (100+ msg/sec): ~0.1ms per message (optimized batching)
- **Per-message latency**: ~0.1-0.5ms (Unix socket + Go efficiency)
- **Batching**: More intelligent batching algorithms in Go
- **Resource usage**: Significantly lower CPU/memory per message

### 📊 Feature & Performance Comparison

| Feature | Agent Mode | Direct API Mode |
|---------|------------|-----------------|
| **Performance (Light Load)** | ~0.5ms/msg | ~2-5ms/msg |
| **Performance (Heavy Load)** | ~0.1ms/msg (batched) | ~0.5-1ms/msg (batched) |
| **Message Batching** | ✅ Intelligent (10-500 msgs) | ✅ True HTTP batching (10-500 msgs) |
| **Offline Storage** | ✅ SQLite persistence | ✅ SQLite persistence |
| **Connection Pooling** | ✅ Optimized Go HTTP/2 pools | ✅ httpx connection pooling |
| **Automatic Retries** | ✅ Built-in agent logic | ✅ SDK retry mechanisms |
| **Resource Usage** | ✅ Low (shared Go process) | ⚠️ Higher (Python overhead) |
| **CPU/Memory Adaptation** | ✅ Dynamic batching | ❌ Fixed behavior |
| **Multi-App/Language Support** | ✅ Single agent serves all | ❌ Each app manages own connection |
| **Setup Complexity** | ⚠️ Requires agent install | ✅ Simple (SDK only) |
| **Network Resilience** | ✅ Agent handles outages | ✅ SDK handles outages |
| **Debugging** | ⚠️ Two-component system | ✅ Direct HTTP visibility |
| **Deployment** | ⚠️ Two processes to manage | ✅ Single process |

### 🏆 Key Differentiators

**Agent Mode Advantages:**

- **Intelligent Batching**: Combines multiple messages into single HTTP requests (major performance gain)
- **Go Performance**: Compiled efficiency vs Python interpreted overhead  
- **Resource Efficiency**: Single optimized process serves multiple Python applications
- **Adaptive Behavior**: Automatically adjusts batching based on system load

**Direct API Mode Advantages:**

- **Simplicity**: No additional components to install or manage
- **Direct Control**: Full visibility into HTTP requests and responses
- **Single Process**: Easier debugging and deployment
- **Immediate Feedback**: Each publish() call gets direct server response

### 💡 Choosing the Right Mode

**Use Direct API Mode when:**

- **Simplicity is priority**: Quick setup, no additional
components
- **Development/Testing**: Prototyping, debugging, local development
- **Low to moderate volume**: < 50 messages per second
- **Deployment constraints**: Can't install additional services
- **Direct feedback needed**: Want immediate HTTP responses per message

**Use Nano Agent Mode when:**

- **Performance is priority**: Need maximum throughput and lowest latency  
- **High volume**: > 50 messages per second
- **Production environments**: Need optimized resource usage
- **Multiple applications**: Sharing agent across several Python processes
- **Multi-language environment**: Different programming languages on same host
- **Centralized management**: Want single point for configuration and monitoring
- **Resource constrained**: Every CPU cycle and MB matters

## Installation

```bash
pip install tendrl
```

## Basic Usage

```python
from tendrl import Client

# Initialize client with direct API key
client = Client(mode="api", api_key="your_key")

# Or use environment variable
# export TENDRL_KEY=your_key
client = Client(mode="api")

# One-time data collection using decorator
@client.tether(tags=["metrics"])
def collect_metrics():
    return {
        "cpu_usage": 42.0,
        "memory": 84.0
    }

# Periodic data collection
@client.tether(tags=["system"], interval=60)
def system_stats():
    return {
        "uptime": 3600,
        "load": 1.5
    }

# Start the client
client.start()

## Headless Mode (Pure SDK)

For simple synchronous publishing without background processing:

```python
# Headless mode - no background threads, direct publishing
client = Client(mode="api", api_key="your_key", headless=True)

# No need to call client.start() in headless mode
# All publish() calls are synchronous and return immediately

# Direct publishing
response = client.publish({"sensor": "temp", "value": 23.5})

# Decorators also work synchronously
@client.tether(tags=["metrics"])
def get_data():
    return {"metric": "value"}

get_data()  # Sends immediately, no queuing
```

**Use headless mode for:**

- Simple scripts that send a few messages and exit
- Serverless/Lambda functions  
- When you need immediate responses and full control
- When you don't want background threads

## API Reference

### Client Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **Core Settings** |
| `mode` | `str` | `"api"` | Operating mode: `"api"` (direct HTTP) or `"agent"` (Unix socket) |
| `api_key` | `str` | `None` | API key for authentication (or use `TENDRL_KEY` env var) |
| `headless` | `bool` | `False` | Pure SDK mode - no background processing, synchronous calls |
| `debug` | `bool` | `False` | Enable debug logging output |
| **Performance & Batching** |
| `target_cpu_percent` | `float` | `65.0` | Target CPU usage for dynamic batch sizing |
| `target_mem_percent` | `float` | `75.0` | Target memory usage for dynamic batch sizing |
| `min_batch_size` | `int` | `10` | Minimum messages per batch |
| `max_batch_size` | `int` | `100` | Maximum messages per batch |
| `min_batch_interval` | `float` | `0.1` | Minimum seconds between batches |
| `max_batch_interval` | `float` | `1.0` | Maximum seconds between batches |
| `max_queue_size` | `int` | `1000` | Maximum size of the message queue |
| **Offline Storage** |
| `offline_storage` | `bool` | `False` | Enable message persistence during outages |
| `db_path` | `str` | `"tendrl_offline.db"` | Custom path for offline storage database |
| **Advanced** |
| `check_msg_rate` | `float` | `3.0` | Message check frequency in seconds (server callbacks) |
| `callback` | `Callable` | `None` | Optional callback function for server messages |

### Message Callbacks

```python
# Set up callback to handle incoming messages
def message_handler(message):
    # Process incoming message
    print(f"Received: {message['msg_type']} from {message['source']}")
    return True  # Return False if processing fails

client.set_message_callback(message_handler)

# Configure checking behavior (optional)
client.set_message_check_rate(5.0)  # Check every 5 seconds (default: 3.0)
client.set_message_check_limit(10)  # Max messages per check (default: 1)

# Manual message check (works in any mode)
messages = client.check_messages()
```

### IncomingMessage Structure

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `msg_type` | `str` | Message type identifier (e.g., "command", "notification", "alert") | ✅ Yes |
| `source` | `str` | Sender's resource path (set by server) | ✅ Yes |
| `dest` | `str` | Destination entity identifier | ❌ Optional |
| `timestamp` | `str` | RFC3339 timestamp (set by server) | ✅ Yes |
| `data` | `dict/list/any` | The actual message payload (can be any JSON type) | ✅ Yes |
| `context` | `dict` | Message metadata | ❌ Optional |
| `request_id` | `str` | Request identifier (if message was a request) | ❌ Optional |

### Message Context Structure

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `tags` | `List[str]` | Message tags for categorization | ❌ Optional |
| `dynamicActions` | `dict` | Server-side validation results | ❌ Optional |

#### How It Works

1. **Background Checking**: In standard mode, the SDK automatically checks for messages every 3 seconds (configurable)
2. **Manual Checking**: You can call `check_messages()` manually in any mode
3. **Callback Execution**: Your callback function is called for each incoming message
4. **Error Handling**: Failed callbacks don't stop other message processing
5. **Connectivity Aware**: Automatically handles network failures and updates connectivity state

### Message Publishing

```python
# Direct message publishing
client.publish(
    msg: dict,                   # Message data
    tags: List[str] = None,      # Message tags
    entity: str = "",            # Send to another entity
    wait_response: bool = False, # Wait for response
    timeout: int = 5             # Response timeout
) -> str:                        # Returns message ID if wait_response=True
```

### Tether Decorator

```python
@client.tether(
    tags: List[str] = None,      # Message tags
    write_offline: bool = False,  # Enable offline storage
    db_ttl: int = 200,           # Offline storage TTL
    entity: str = "",            # Send to another entity
)
```

## Advanced Usage

### Resource Monitoring

```python
# Get current system metrics
metrics = client.get_system_metrics()
print(f"CPU: {metrics.cpu_usage}%")
print(f"Memory: {metrics.memory_usage}%")
print(f"Queue Load: {metrics.queue_load}%")

# Configure resource limits
client = Client(
    target_cpu_percent=60.0,
    target_mem_percent=70.0
)
```

### Batch Processing Configuration

```python
client = Client(
    min_batch_size=10,
    max_batch_size=500,
    min_batch_interval=0.1,
    max_batch_interval=1.0
)
```

### Offline Storage

```python
# Enable offline storage
client = Client(
    offline_storage=True,
    db_path="/path/to/storage.db"
)

# Tether with offline storage
@client.tether(tags=["metrics"], write_offline=True, db_ttl=3600)
def collect_metrics():
    return {"data": "value"}
```

### Logging Configuration

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

client = Client(debug=True)
```

## Best Practices

1. Resource Management

- Use appropriate batch sizes
- Monitor system metrics
- Implement proper cleanup

2. Error Handling

- Use retries for transient failures
- Log errors appropriately
- Handle offline scenarios

3. Performance

- Use batch processing
- Monitor queue size
- Configure appropriate intervals

4. Security

- Secure API keys
- Use HTTPS
- Validate input data

## Troubleshooting

Common issues and solutions:

### Windows Issues

1. Agent Connection Error

```python
# Ensure Tendrl Nano Agent is running
# Check if tendrl-agent.exe process is active in Task Manager
# Or run: tasklist /FI "IMAGENAME eq tendrl-agent.exe"

# Start the agent if not running
# tendrl-agent.exe -apiKey=YOUR_API_KEY
```

2. Agent Not Found

```python
# Verify Windows version compatibility
import platform
print(f"Windows version: {platform.version()}")
# Requires Windows 10 1803+ or Windows Server 2019+

# Ensure agent directory exists
import os
os.makedirs("C:\\ProgramData\\tendrl", exist_ok=True)
```

### General Issues

1. Connection Issues

```python
# Increase timeout
client = Client(timeout=10)
```

2. Queue Full

```python
# Increase batch processing
client = Client(
    max_batch_size=1000,
    min_batch_interval=0.05
)
```

3. High Memory Usage

```python
# Adjust batch size
client = Client(
    max_batch_size=100,
    target_mem_percent=60.0
)
```

4. Message Loss

```python
# Enable offline storage
client = Client(
    offline_storage=True,
    db_ttl=3600
)
```

## Offline Message Flow

The following shows how messages with tags are handled during offline periods:

```sh
@tether(tags=['sensor', 'prod'])
         ↓
   Message Created
         ↓
   Connection Check
         ↓
    ┌─────────────┐
    │  Online?    │
    └─────────────┘
         ↓
    ┌────┴────┐
    │         │
   Yes       No
    │         │
    ↓         ↓
Send with   Store in SQLite
  Tags      WITH TAGS
    │         │
    │    Connection Restored
    │         ↓
    │    Batch Processing (50 msgs)
    │         ↓
    │    Parse data + tags
    │         ↓
    │    Reconstruct message
    │         ↓
    └─────────┘
         ↓
   Send to Server
         ↓
Server processes webhook
    with tags
```

### Key Features

- **Tags Preservation**: Tags are stored with offline messages and restored when sent
- **Batched Processing**: Large offline backlogs are processed in manageable batches (50 messages)
- **Fault Tolerance**: Failed batches don't affect successfully sent messages
- **Webhook Compatibility**: Server receives messages with proper tags for processing

> **Note**: The client uses queue-based processing, making it effectively non-blocking. If you need async APIs in an async application, you can wrap calls using `asyncio.to_thread(client.publish, data)`.

### Using with Tendrl Nano Agent

For optimal performance (see [Operating Modes](#operating-modes) comparison), use the [Tendrl Nano Agent](`https://tendrl.com/docs/nano_agent/`):

#### 1. Start the Tendrl Nano Agent

**Windows:**

```powershell
# Download tendrl-agent.exe and run
tendrl-agent.exe -apiKey=YOUR_API_KEY
```

**Unix/Linux:**

```bash
# Download tendrl-agent and run
export TENDRL_API_KEY=your_key
./tendrl-agent
```

#### 2. Connect Python SDK to Agent

```python
from tendrl import Client

# Agent mode - connects to local Tendrl Nano Agent
client = Client(mode="agent")
client.start()

# Publish data through the agent
client.publish({"sensor": "temperature", "value": 23.5})
```

#### Alternative: Direct API Mode

```python
# Direct API mode - connects directly to Tendrl servers
client = Client(mode="api", api_key="your_key")
client.start()
```

> **Performance Note**: Agent mode provides 5-20x better performance than direct API mode. See the [Operating Modes](#operating-modes) section for detailed comparison.
