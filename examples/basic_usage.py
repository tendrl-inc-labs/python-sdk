#!/usr/bin/env python3
"""
Basic Tendrl SDK Usage Example

This example demonstrates the fundamental features of the Tendrl Python SDK:
- Direct API mode vs Agent mode
- Basic publish operations
- Receiving and handling incoming messages via callbacks
- Using decorators for automatic data collection
- Error handling and graceful shutdown
"""

import sys
import time
import signal
from datetime import datetime, UTC
from tendrl import Client

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down gracefully...")
    client.stop()
    sys.exit(0)

# Set up signal handler for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)

# Initialize client (uses environment variable TENDRL_KEY if available)
client = Client(
    mode="api",  # Use "agent" for Nano Agent mode
    debug=True,
    max_batch_size=50,
    max_queue_size=1000,
    check_msg_rate=3,  # Check for incoming messages every 3 seconds
    check_msg_limit=10  # Retrieve up to 10 messages per check
)

def message_callback(message):
    """
    Callback function to handle incoming messages from the server.
    
    This callback is called automatically when messages are received via check_msg().
    The message structure includes:
    - msg_type: Type of message (e.g., "publish", "command")
    - data: The message payload (dict, list, or any JSON type)
    - source: Sender's resource path
    - timestamp: RFC3339 timestamp
    - tags: Optional list of string tags
    """
    print("\n" + "="*60)
    print("📨 INCOMING MESSAGE RECEIVED")
    print("="*60)
    
    # Check message type
    msg_type = message.get("msg_type", "unknown")
    print(f"Message Type: {msg_type}")
    
    # Get source information
    source = message.get("source", "unknown")
    print(f"From: {source}")
    
    # Get timestamp
    timestamp = message.get("timestamp", "unknown")
    print(f"Timestamp: {timestamp}")
    
    # Get message data
    data = message.get("data", {})
    print(f"Data Type: {type(data).__name__}")
    print(f"Data Content: {data}")
    
    # Check for tags
    tags = message.get("tags", [])
    if tags:
        print(f"Tags: {', '.join(tags)}")
    
    print("="*60 + "\n")
    
    # Return True to indicate successful processing
    # Return False if processing failed (won't stop other messages)
    return True

# Set the callback for incoming messages
client.callback = message_callback
client.start()

print("Starting Tendrl SDK Basic Usage Example...")
print("Press Ctrl+C to stop\n")
print("📡 The client will automatically check for incoming messages every 3 seconds")
print("   Messages will be processed through the message_callback function\n")

# Example 1: Simple string message
print("1. Sending simple string message...")
try:
    response = client.publish("Hello from Tendrl SDK!", wait_response=True)
    print(f"   Response: {response}\n")
except Exception as e:
    print(f"   Error: {e}\n")

# Example 2: Structured data payload
print("2. Sending structured application data...")
app_metrics = {
    "application": "web-server",
    "version": "1.2.3",
    "environment": "production",
    "metrics": {
        "requests_per_second": 145.7,
        "response_time_ms": 23.4,
        "error_rate": 0.02,
        "active_connections": 1247
    },
    "timestamp": datetime.now(UTC).isoformat(),
    "host": "web-01.example.com"
}

try:
    client.publish(app_metrics, wait_response=True)
    print("   ✓ Application metrics sent\n")
except Exception as e:
    print(f"   Error: {e}\n")

# Example 3: Using decorators for automatic collection
print("3. Using decorators for automatic data collection...")

@client.tether(tags=["system-metrics", "monitoring"])
def collect_system_info():
    """Collect system information automatically"""
    import psutil
    import platform
    
    return {
        "system": {
            "platform": platform.system(),
            "release": platform.release(),
            "architecture": platform.architecture()[0]
        },
        "cpu": {
            "usage_percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "frequency_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "usage_percent": psutil.virtual_memory().percent
        },
        "disk": {
            "usage_percent": psutil.disk_usage('/').percent,
            "free_gb": round(psutil.disk_usage('/').free / (1024**3), 2)
        },
        "collection_time": datetime.now(UTC).isoformat()
    }

# Collect and send system metrics
try:
    collect_system_info()  # This will automatically queue and send
    print("   ✓ System metrics queued for sending\n")
except Exception as e:
    print(f"   Error collecting system metrics: {e}\n")

# Example 4: Batch sending multiple messages
print("4. Batch sending multiple IoT sensor readings...")
sensor_data = []
for i in range(5):
    sensor_reading = {
        "sensor_id": f"temp_sensor_{i:02d}",
        "location": f"Zone-{chr(65+i)}",  # Zone-A, Zone-B, etc.
        "readings": {
            "temperature_c": 20.5 + (i * 2.3),
            "humidity_pct": 45.2 + (i * 3.1),
            "pressure_hpa": 1013.25 + (i * 1.7)
        },
        "battery_level": 85 - (i * 5),
        "signal_strength": -42 - (i * 3),
        "timestamp": datetime.now(UTC).isoformat(),
        "device_type": "environmental_sensor",
        "firmware_version": "2.1.4"
    }
    sensor_data.append(sensor_reading)

# Send all sensor data
for data in sensor_data:
    try:
        client.publish(data)  # Non-blocking send
    except Exception as e:
        print(f"   Error sending sensor data: {e}")

print("   ✓ All sensor readings queued for batch sending\n")

# Give time for batched messages to be sent
print("Waiting for all messages to be sent...")
time.sleep(3)

print("\n" + "="*60)
print("Example completed successfully!")
print("="*60)
print("\nThe client is now running and will:")
print("  ✓ Continue checking for incoming messages every 3 seconds")
print("  ✓ Process any received messages through the callback")
print("  ✓ Keep the connection alive for receiving messages")
print("\nTo test message receiving:")
print("  1. Send a message to this entity from another entity or the web UI")
print("  2. The message will be automatically received and processed")
print("  3. Watch the console for incoming message notifications")
print("\nPress Ctrl+C to stop.\n")

# Keep the client running to receive messages
try:
    while True:
        # The client automatically checks for messages in the background
        # You can also manually check if needed:
        # client.check_msg()
        time.sleep(1)
except KeyboardInterrupt:
    pass 