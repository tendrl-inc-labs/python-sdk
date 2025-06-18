#!/usr/bin/env python3
"""
Simple GPIO Sensor Example with GPIOZero

A beginner-friendly example using common, inexpensive sensors:
- Temperature sensor (DS18B20 or DHT22)
- Motion sensor (PIR)
- Button input
- LED status indicator

Hardware needed (~$15-20):
- Raspberry Pi (any model)
- DS18B20 temperature sensor ($2-3)
- PIR motion sensor ($2-3)  
- Push button ($0.50)
- LED + resistor ($0.50)
- Jumper wires ($5)

Simple wiring:
- DS18B20: Data to GPIO 4 (needs 4.7kΩ pullup to 3.3V)
- PIR: OUT to GPIO 14, VCC to 5V, GND to GND
- Button: One side to GPIO 2, other to GND
- LED: Long leg to GPIO 18 via 220Ω resistor, short leg to GND
"""

import sys
import time
import signal
from datetime import datetime
from tendrl import Client

# Check for GPIO availability
try:
    from gpiozero import LED, Button, MotionSensor
    from w1thermsensor import W1ThermSensor
    GPIO_AVAILABLE = True
    print("✅ GPIO libraries available")
except ImportError as e:
    GPIO_AVAILABLE = False
    print(f"⚠️  GPIO libraries not found: {e}")
    print("💡 Install with: pip install gpiozero w1thermsensor")
    print("🔧 Running in simulation mode")

# Configuration
READ_INTERVAL = 10  # seconds
DEVICE_NAME = "RaspberryPi-01"

class SimpleGPIOSensors:
    def __init__(self):
        self.simulation_mode = not GPIO_AVAILABLE
        self.start_time = datetime.utcnow()
        self.motion_count = 0
        self.button_count = 0
        
        if not self.simulation_mode:
            self._setup_gpio()
        else:
            self._setup_simulation()
    
    def _setup_gpio(self):
        """Initialize GPIO components"""
        try:
            # Hardware setup
            self.status_led = LED(18)
            self.button = Button(2, pull_up=True)
            self.motion_sensor = MotionSensor(14)
            self.temp_sensor = W1ThermSensor()
            
            # Event handlers
            self.motion_sensor.when_motion = self._motion_detected
            self.button.when_pressed = self._button_pressed
            
            # Turn on status LED to show we're ready
            self.status_led.on()
            print("✅ GPIO sensors initialized")
            
        except Exception as e:
            print(f"❌ GPIO setup failed: {e}")
            self.simulation_mode = True
            self._setup_simulation()
    
    def _setup_simulation(self):
        """Setup simulation variables"""
        import random
        self.sim_temp = 20.0
        self.sim_motion = False
        print("🎮 Simulation mode active")
    
    def _motion_detected(self):
        """Handle motion detection"""
        self.motion_count += 1
        print(f"🚶 Motion detected! (Count: {self.motion_count})")
    
    def _button_pressed(self):
        """Handle button press"""
        self.button_count += 1
        print(f"🔘 Button pressed! (Count: {self.button_count})")
    
    def read_sensors(self):
        """Read all sensor values"""
        if not self.simulation_mode:
            # Blink LED during reading
            self.status_led.blink(0.1, 0.1, 1)
        
        # Read temperature
        try:
            if self.simulation_mode:
                import random
                # Simulate temperature drift
                self.sim_temp += random.uniform(-0.5, 0.5)
                self.sim_temp = max(15, min(30, self.sim_temp))
                temperature = round(self.sim_temp, 1)
            else:
                temperature = round(self.temp_sensor.get_temperature(), 1)
        except Exception as e:
            print(f"⚠️  Temperature sensor error: {e}")
            temperature = None
        
        # Check motion
        try:
            if self.simulation_mode:
                import random
                motion_active = random.random() < 0.1  # 10% chance
                if motion_active:
                    self.motion_count += 1
            else:
                motion_active = self.motion_sensor.motion_detected
        except Exception as e:
            print(f"⚠️  Motion sensor error: {e}")
            motion_active = None
        
        # Create sensor reading
        reading = {
            "device_name": DEVICE_NAME,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_minutes": round((datetime.utcnow() - self.start_time).total_seconds() / 60, 1),
            "simulation_mode": self.simulation_mode,
            
            "temperature": {
                "celsius": temperature,
                "fahrenheit": round(temperature * 9/5 + 32, 1) if temperature else None,
                "status": "ok" if temperature else "error"
            },
            
            "motion": {
                "detected": motion_active,
                "total_events": self.motion_count,
                "status": "ok" if motion_active is not None else "error"
            },
            
            "user_input": {
                "button_presses": self.button_count
            }
        }
        
        return reading
    
    def cleanup(self):
        """Clean up GPIO"""
        if not self.simulation_mode:
            try:
                self.status_led.off()
                print("🧹 GPIO cleaned up")
            except:
                pass

def signal_handler(signum, frame):
    """Handle Ctrl+C"""
    print("\nShutting down...")
    sensors.cleanup()
    client.stop()
    sys.exit(0)

# Setup
signal.signal(signal.SIGINT, signal_handler)

# Initialize Tendrl client
client = Client(
    mode="api",
    debug=True,
    max_batch_size=10,
    max_queue_size=100
)

client.start()
sensors = SimpleGPIOSensors()

print("🥧 Simple GPIO Sensor Example")
print(f"📍 Device: {DEVICE_NAME}")
print(f"📊 Reading every {READ_INTERVAL} seconds")
print(f"🔧 Mode: {'Hardware' if not sensors.simulation_mode else 'Simulation'}")
print("📡 Press Ctrl+C to stop\n")

# Environmental status decorator
@client.tether(tags=["environment", "raspberry-pi", "simple"])
def environmental_status():
    """Send environmental summary"""
    temp = sensors.sim_temp if sensors.simulation_mode else None
    try:
        if not sensors.simulation_mode:
            temp = sensors.temp_sensor.get_temperature()
    except:
        temp = None
    
    if temp:
        if temp < 18:
            comfort = "cool"
        elif temp > 25:
            comfort = "warm"
        else:
            comfort = "comfortable"
    else:
        comfort = "unknown"
    
    return {
        "environmental_status": {
            "device_name": DEVICE_NAME,
            "timestamp": datetime.utcnow().isoformat(),
            "temperature_status": comfort,
            "activity_level": "active" if sensors.motion_count > 0 else "quiet",
            "user_interactions": sensors.button_count
        }
    }

# Main loop
reading_count = 0

try:
    while True:
        # Read sensors
        sensor_data = sensors.read_sensors()
        client.publish(sensor_data)
        reading_count += 1
        
        # Display status
        temp = sensor_data["temperature"]["celsius"]
        motion = sensor_data["motion"]["detected"]
        
        print(f"📊 Reading #{reading_count}: "
              f"🌡️ {temp}°C, "
              f"🚶 Motion: {'Yes' if motion else 'No'}, "
              f"🔘 Buttons: {sensor_data['user_input']['button_presses']}")
        
        # Send environmental summary every 5 readings
        if reading_count % 5 == 0:
            environmental_status()
            print("🌡️  Environmental summary sent")
        
        # Alert on extreme temperature
        if temp and (temp > 30 or temp < 10):
            alert = {
                "alert": {
                    "type": "temperature_alert",
                    "device": DEVICE_NAME,
                    "message": f"Temperature is {temp}°C",
                    "severity": "warning",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            client.publish(alert)
            print(f"🚨 Temperature alert: {temp}°C")
        
        time.sleep(READ_INTERVAL)

except KeyboardInterrupt:
    pass

print(f"\n✅ Completed {reading_count} readings")
print(f"🚶 Motion events: {sensors.motion_count}")
print(f"🔘 Button presses: {sensors.button_count}")

sensors.cleanup()
client.stop() 