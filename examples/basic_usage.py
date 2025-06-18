#!/usr/bin/env python3
"""
Basic Tendrl SDK Usage Example

This example demonstrates the fundamental features of the Tendrl Python SDK:
- Direct API mode vs Agent mode
- Basic publish operations
- Using decorators for automatic data collection
- Error handling and graceful shutdown
"""

import sys
import time
import signal
from datetime import datetime
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
    max_queue_size=1000
)

def callback(response):
    """Optional callback to handle server responses"""
    print(f"✓ Message sent successfully at {response.get('timestamp')}")
    print(f"  Server response: {response.get('status', 'OK')}")

client.callback = callback
client.start()

print("Starting Tendrl SDK Basic Usage Example...")
print("Press Ctrl+C to stop\n")

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
    "timestamp": datetime.utcnow().isoformat(),
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
        "collection_time": datetime.utcnow().isoformat()
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
        "timestamp": datetime.utcnow().isoformat(),
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

print("\nExample completed successfully!")
print("The client will continue running. Press Ctrl+C to stop.")

# Keep the client running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass 