# Tendrl Python SDK Examples

This directory contains practical examples demonstrating the Tendrl Python SDK with real-world hardware integration. These examples focus on IoT and sensor applications, perfect for makers, educators, and developers getting started with data collection.

## 📋 Example Overview

| Example | Description | Use Case | Complexity |
|---------|-------------|----------|------------|
| [`basic_usage.py`](#basic-usage) | Fundamental SDK operations | Learning the basics | ⭐ Beginner |
| [`simple_gpio_sensors.py`](#simple-gpio-sensors) | Basic Raspberry Pi sensors | Maker projects, Home automation | ⭐ Beginner |
| [`raspberry_pi_sensors.py`](#raspberry-pi-sensor-hub) | Advanced GPIO sensor hub | Professional IoT, Edge computing | ⭐⭐ Intermediate |

## 🚀 Quick Start

### Prerequisites

```bash
# Install the Tendrl SDK
pip install git+https://github.com/tendrl-inc-labs/contact-python

# Install optional dependencies for advanced examples
pip install psutil  # For system metrics in basic_usage.py

# For Raspberry Pi GPIO examples
pip install gpiozero w1thermsensor  # Real hardware sensors
```

### Environment Setup

```bash
# Set your Tendrl API key
export TENDRL_KEY="your_api_key_here"


### Running Examples

```bash
# Make examples executable
chmod +x examples/*.py

# Run any example
python examples/basic_usage.py
```

## 📚 Detailed Examples

### Basic Usage

**File:** `basic_usage.py`  
**Complexity:** ⭐ Beginner  
**Duration:** ~30 seconds

**What it demonstrates:**

- Client initialization and configuration
- Direct API vs Agent mode
- Simple string and structured data publishing
- Using decorators for automatic data collection
- System metrics collection with `psutil`
- Error handling and graceful shutdown

**Key Features:**

- 🔌 Mode switching (API/Agent)
- 📊 System metrics (CPU, memory, disk)
- 🏷️ Tagging and categorization
- 🔄 Batch processing
- ⚡ Response handling

**Sample Payloads:**

```python
# Application metrics
{
    "application": "web-server",
    "version": "1.2.3",
    "environment": "production",
    "metrics": {
        "requests_per_second": 145.7,
        "response_time_ms": 23.4,
        "error_rate": 0.02
    }
}

# System information
{
    "system": {"platform": "Darwin", "architecture": "64bit"},
    "cpu": {"usage_percent": 45.2, "count": 8},
    "memory": {"total_gb": 16.0, "usage_percent": 62.5}
}
```

---

### Simple GPIO Sensors

**File:** `simple_gpio_sensors.py`  
**Complexity:** ⭐ Beginner  
**Duration:** ~2 minutes  
**Hardware Cost:** ~$15-20

**What it demonstrates:**

- Real Raspberry Pi GPIO sensor integration
- Basic sensor types (temperature, motion, button)
- Hardware-software integration
- Event-driven programming
- Automatic fallback to simulation mode

**Key Features:**

- 🌡️ **DS18B20 temperature sensor**: Accurate digital temperature
- 🚶 **PIR motion sensor**: Passive infrared motion detection
- 🔘 **Push button**: User input handling
- 💡 **Status LED**: Visual feedback
- 🎮 **Simulation mode**: Works without hardware

**Hardware Requirements:**

- Raspberry Pi (any model with GPIO)
- DS18B20 temperature sensor ($2-3)
- PIR motion sensor ($2-3)
- Push button ($0.50)
- LED + 220Ω resistor ($0.50)
- Jumper wires ($5)
- Breadboard ($5)

**Simple Wiring:**

DS18B20:  Data → GPIO 4 (with 4.7kΩ pullup to 3.3V)
PIR:      OUT → GPIO 14, VCC → 5V, GND → GND
Button:   One side → GPIO 2, other → GND
LED:      Long leg → GPIO 18 via 220Ω resistor → GND

**Sample Payloads:**

```python
# Basic sensor reading
{
    "device_name": "RaspberryPi-01",
    "timestamp": "2024-06-18T14:30:00Z",
    "simulation_mode": false,
    "temperature": {
        "celsius": 22.5,
        "fahrenheit": 72.5,
        "status": "ok"
    },
    "motion": {
        "detected": false,
        "total_events": 3,
        "status": "ok"
    },
    "user_input": {
        "button_presses": 1
    }
}

# Environmental summary
{
    "environmental_status": {
        "device_name": "RaspberryPi-01",
        "temperature_status": "comfortable",
        "activity_level": "quiet",
        "user_interactions": 1
    }
}
```

---

### Raspberry Pi Sensor Hub

**File:** `raspberry_pi_sensors.py`  
**Complexity:** ⭐⭐ Intermediate  
**Duration:** ~5 minutes  
**Hardware Cost:** ~$30-40

**What it demonstrates:**

- Professional IoT sensor integration
- Multiple sensor types with advanced features
- LED status indicators and buzzer alerts
- Environmental monitoring and comfort analysis
- Device health monitoring
- Production-ready error handling

**Key Features:**

- 🌡️ **Temperature monitoring**: DS18B20 with trend analysis
- 🚶 **Motion detection**: PIR with event counting and timing
- 💡 **Light sensing**: LDR with MCP3008 ADC for accurate readings
- 🔘 **User interaction**: Button input with event handling
- 🚨 **Alert system**: Buzzer and LED indicators
- 📊 **Environmental analysis**: Comfort index calculation
- ❤️ **Device health**: System monitoring with psutil

**Hardware Requirements:**

- Raspberry Pi with GPIO
- DS18B20 temperature sensor
- PIR motion sensor
- Light sensor (LDR) + MCP3008 ADC
- Push button + pull-up resistor
- Status LEDs (3x) + resistors
- Buzzer (optional)
- Jumper wires and breadboard

**Advanced Wiring:**

DS18B20:    Data → GPIO 4 (4.7kΩ pullup)
PIR:        OUT → GPIO 14
Button:     GPIO 2 (pull-up enabled)
Status LED: GPIO 18
Error LED:  GPIO 23
Activity:   GPIO 24
Buzzer:     GPIO 25
MCP3008:    SPI connection for light sensor

## 🔧 Configuration Options

### Client Configuration

```python
from tendrl import Client

# Basic configuration
client = Client(
    mode="api",           # "api" or "agent"
    api_key="your_key",   # Or use TENDRL_KEY env var
    debug=True,           # Enable debug logging
    max_batch_size=50,    # Messages per batch
    max_queue_size=1000   # Max queued messages
)

# Advanced configuration
client = Client(
    mode="agent",
    socket_path="/tmp/tendrl.sock",  # Custom socket path
    retry_attempts=3,                 # Connection retries
    timeout_seconds=30,               # Request timeout
    callback=my_callback_function     # Response handler
)
```

## 📊 Performance Tips

### GPIO/Hardware Applications

- Use smaller batch sizes (10-50 messages) for sensor data
- Implement proper GPIO cleanup on shutdown
- Handle hardware failures gracefully with simulation fallback
- Monitor sensor health and connectivity

### Battery-Powered Devices

- Adjust reading intervals to conserve power
- Use agent mode for better efficiency
- Implement intelligent batching based on battery level
- Add low-battery alerts and graceful degradation

### Production IoT Deployment

- Set appropriate sensor timeouts
- Implement device health monitoring
- Use structured logging for debugging
- Monitor sensor performance metrics
- Set up alerting for device failures

## 🔍 Troubleshooting

### Common Issues

**GPIO/Hardware Problems:**

```bash
# Check GPIO libraries
python -c "import gpiozero; print('GPIO available')"
python -c "import w1thermsensor; print('Temperature sensor available')"

# Enable simulation mode for testing
export GPIO_SIMULATION=true
python examples/simple_gpio_sensors.py
```

**Sensor Issues:**

```python
# Check sensor status
print(f"Temperature sensor status: {sensor.status}")

# Implement graceful degradation
try:
    temperature = sensor.read_temperature()
except Exception as e:
    print(f"Sensor error: {e}")
    temperature = None  # Continue without this reading
```

**Raspberry Pi Specific:**

```bash
# Check 1-Wire is enabled for DS18B20
ls /sys/bus/w1/devices/

# Check GPIO permissions
sudo usermod -a -G gpio $USER
```

## 📖 Additional Resources

- [Tendrl Python SDK Documentation](https://tendrl.com/docs/python_sdk/)
- [API Reference](https://tendrl.com/docs/api/)
- [Best Practices Guide](https://tendrl.com/docs/best_practices/)
- [Support Forum](https://community.tendrl.com/)

## 🤝 Contributing

Found an issue or want to improve an example? Please:

1. Check existing issues
2. Create a detailed bug report or feature request
3. Submit a pull request with your improvements

## 📄 License

These examples are provided under the same license as the Tendrl Python SDK. See the [LICENSE](../LICENSE) file for details.
