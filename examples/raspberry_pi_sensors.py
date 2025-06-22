#!/usr/bin/env python3
"""
Raspberry Pi IoT Sensor Example with GPIOZero

This example demonstrates real-world IoT sensor integration using gpiozero:
- DS18B20 temperature sensor (1-Wire)
- PIR motion sensor
- Light sensor (LDR with MCP3008 ADC)
- Push button input
- LED status indicators
- Buzzer for alerts

Hardware Requirements:
- Raspberry Pi (any model with GPIO)
- DS18B20 temperature sensor
- PIR motion sensor 
- Light sensor (LDR) + MCP3008 ADC
- Push button + pull-down resistor
- LEDs (status, error, activity)
- Buzzer (optional)
- Jumper wires and breadboard

Wiring:
- DS18B20: Data pin to GPIO 4 (with 4.7kΩ pull-up resistor)
- PIR sensor: Output to GPIO 14
- Button: One side to GPIO 2, other to GND (with pull-up enabled)
- Status LED: GPIO 18
- Error LED: GPIO 23  
- Activity LED: GPIO 24
- Buzzer: GPIO 25 (optional)
- MCP3008: SPI connection for light sensor
"""

import sys
import time
import signal
import random
import math
from datetime import datetime
from tendrl import Client

# Hardware availability check
try:
    from gpiozero import (
        LED, Button, Buzzer, 
        MotionSensor, MCP3008,
        Device
    )
    from w1thermsensor import W1ThermSensor, NoSensorFoundError
    GPIO_AVAILABLE = True
    print("✅ GPIO hardware libraries available")
except ImportError as e:
    GPIO_AVAILABLE = False
    print(f"⚠️  GPIO libraries not available: {e}")
    print("💡 Install with: pip install gpiozero w1thermsensor")
    print("🔧 This example will run in simulation mode")

# Configuration
SENSOR_READ_INTERVAL = 5  # seconds
SIMULATION_DURATION = 300  # seconds (5 minutes)
DEVICE_ID = "rpi-sensor-01"
LOCATION = "Home Office"

class RaspberryPiSensorHub:
    def __init__(self, simulation_mode=False):
        self.simulation_mode = simulation_mode or not GPIO_AVAILABLE
        self.start_time = datetime.utcnow()
        self.motion_events = 0
        self.button_presses = 0
        self.last_motion_time = None
        self.sensor_errors = []
        
        if not self.simulation_mode:
            self._setup_hardware()
        else:
            print("🎮 Running in simulation mode - no hardware required")
            self._setup_simulation()
    
    def _setup_hardware(self):
        """Initialize real hardware sensors"""
        try:
            # Status LEDs
            self.status_led = LED(18)
            self.error_led = LED(23)
            self.activity_led = LED(24)
            
            # Sensors
            self.temp_sensor = W1ThermSensor()
            self.motion_sensor = MotionSensor(14)
            self.light_sensor = MCP3008(channel=0)  # Channel 0 of MCP3008
            self.button = Button(2, pull_up=True)
            
            # Optional buzzer
            try:
                self.buzzer = Buzzer(25)
            except:
                self.buzzer = None
                print("⚠️  Buzzer not connected or unavailable")
            
            # Set up event handlers
            self.motion_sensor.when_motion = self._on_motion_detected
            self.motion_sensor.when_no_motion = self._on_motion_stopped
            self.button.when_pressed = self._on_button_pressed
            
            # Indicate successful setup
            self.status_led.on()
            print("✅ Hardware sensors initialized successfully")
            
        except Exception as e:
            print(f"❌ Hardware setup failed: {e}")
            self.simulation_mode = True
            self._setup_simulation()
    
    def _setup_simulation(self):
        """Setup simulation mode variables"""
        import random
        self.simulated_temp = 22.0
        self.simulated_light = 0.5
        self.simulated_motion = False
        self.temp_drift = random.uniform(-0.1, 0.1)
    
    def _on_motion_detected(self):
        """Handle motion detection event"""
        self.motion_events += 1
        self.last_motion_time = datetime.utcnow()
        if not self.simulation_mode and self.buzzer:
            self.buzzer.beep(0.1, 0.1, 2)  # Quick double beep
        print("🚶 Motion detected!")
    
    def _on_motion_stopped(self):
        """Handle motion stopped event"""
        print("🛑 Motion stopped")
    
    def _on_button_pressed(self):
        """Handle button press event"""
        self.button_presses += 1
        print(f"🔘 Button pressed! (Total: {self.button_presses})")
    
    def read_temperature(self):
        """Read temperature from DS18B20 sensor"""
        try:
            if self.simulation_mode:
                # Simulate temperature with drift and noise
                self.simulated_temp += self.temp_drift + random.uniform(-0.5, 0.5)
                self.simulated_temp = max(10, min(40, self.simulated_temp))  # Reasonable range
                return round(self.simulated_temp, 2)
            else:
                temp_c = self.temp_sensor.get_temperature()
                return round(temp_c, 2)
        except Exception as e:
            self.sensor_errors.append(f"Temperature sensor error: {e}")
            return None
    
    def read_light_level(self):
        """Read light level from LDR via MCP3008"""
        try:
            if self.simulation_mode:
                # Simulate day/night cycle
                hour = datetime.utcnow().hour
                if 6 <= hour <= 18:  # Daytime
                    base_light = 0.7 + 0.3 * math.sin((hour - 6) * math.pi / 12)
                else:  # Nighttime
                    base_light = 0.1
                
                # Add some noise
                self.simulated_light = base_light + random.uniform(-0.1, 0.1)
                return max(0, min(1, self.simulated_light))
            else:
                light_value = self.light_sensor.value  # 0.0 to 1.0
                return round(light_value, 3)
        except Exception as e:
            self.sensor_errors.append(f"Light sensor error: {e}")
            return None
    
    def read_motion_status(self):
        """Get current motion sensor status"""
        try:
            if self.simulation_mode:
                # Simulate occasional motion
                if random.random() < 0.05:  # 5% chance per reading
                    self.simulated_motion = True
                    self.motion_events += 1
                    self.last_motion_time = datetime.utcnow()
                else:
                    self.simulated_motion = False
                return self.simulated_motion
            else:
                return self.motion_sensor.motion_detected
        except Exception as e:
            self.sensor_errors.append(f"Motion sensor error: {e}")
            return None
    
    def get_sensor_reading(self):
        """Collect all sensor readings"""
        if not self.simulation_mode:
            try:
                self.activity_led.on()
            except:
                pass
        
        # Read all sensors
        temperature = self.read_temperature()
        light_level = self.read_light_level()
        motion_detected = self.read_motion_status()
        
        # Calculate uptime
        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        
        # Motion detection timing
        seconds_since_motion = None
        if self.last_motion_time:
            seconds_since_motion = (datetime.utcnow() - self.last_motion_time).total_seconds()
        
        reading = {
            "device_id": DEVICE_ID,
            "location": LOCATION,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": round(uptime_seconds, 1),
            "simulation_mode": self.simulation_mode,
            
            # Sensor readings
            "sensors": {
                "temperature": {
                    "value_celsius": temperature,
                    "status": "ok" if temperature is not None else "error",
                    "sensor_type": "DS18B20"
                },
                "light": {
                    "value_normalized": light_level,
                    "value_percent": round(light_level * 100, 1) if light_level is not None else None,
                    "status": "ok" if light_level is not None else "error",
                    "sensor_type": "LDR_MCP3008"
                },
                "motion": {
                    "detected": motion_detected,
                    "total_events": self.motion_events,
                    "seconds_since_last": seconds_since_motion,
                    "status": "ok" if motion_detected is not None else "error",
                    "sensor_type": "PIR"
                }
            },
            
            # User interaction
            "user_input": {
                "button_presses": self.button_presses,
                "last_interaction": datetime.utcnow().isoformat() if self.button_presses > 0 else None
            },
            
            # System status
            "system": {
                "sensor_errors": len(self.sensor_errors),
                "recent_errors": self.sensor_errors[-3:] if self.sensor_errors else [],
                "hardware_status": "simulated" if self.simulation_mode else "connected"
            }
        }
        
        if not self.simulation_mode:
            try:
                self.activity_led.off()
            except:
                pass
        
        return reading
    
    def get_environmental_summary(self):
        """Generate environmental conditions summary"""
        temp = self.read_temperature()
        light = self.read_light_level()
        
        # Determine conditions
        if temp is not None:
            if temp < 18:
                temp_status = "cold"
            elif temp > 26:
                temp_status = "warm"
            else:
                temp_status = "comfortable"
        else:
            temp_status = "unknown"
        
        if light is not None:
            if light < 0.2:
                light_status = "dark"
            elif light > 0.8:
                light_status = "bright"
            else:
                light_status = "moderate"
        else:
            light_status = "unknown"
        
        return {
            "environmental_summary": {
                "device_id": DEVICE_ID,
                "location": LOCATION,
                "timestamp": datetime.utcnow().isoformat(),
                "conditions": {
                    "temperature_status": temp_status,
                    "light_status": light_status,
                    "motion_activity": "active" if self.motion_events > 0 else "quiet"
                },
                "comfort_index": self._calculate_comfort_index(temp, light),
                "recommendations": self._get_recommendations(temp, light)
            }
        }
    
    def _calculate_comfort_index(self, temp, light):
        """Calculate a simple comfort index (0-100)"""
        if temp is None or light is None:
            return None
        
        # Temperature comfort (optimal around 22°C)
        temp_score = max(0, 100 - abs(temp - 22) * 10)
        
        # Light comfort (optimal around 0.6)
        light_score = max(0, 100 - abs(light - 0.6) * 100)
        
        # Combined comfort index
        comfort_index = (temp_score + light_score) / 2
        return round(comfort_index, 1)
    
    def _get_recommendations(self, temp, light):
        """Generate recommendations based on conditions"""
        recommendations = []
        
        if temp is not None:
            if temp < 18:
                recommendations.append("Consider increasing heating")
            elif temp > 26:
                recommendations.append("Consider cooling or ventilation")
        
        if light is not None:
            if light < 0.2:
                recommendations.append("Consider turning on lights")
            elif light > 0.9:
                recommendations.append("Consider closing blinds or curtains")
        
        if not recommendations:
            recommendations.append("Environmental conditions are optimal")
        
        return recommendations
    
    def cleanup(self):
        """Clean up GPIO resources"""
        if not self.simulation_mode:
            try:
                self.status_led.off()
                self.error_led.off()
                self.activity_led.off()
                if self.buzzer:
                    self.buzzer.off()
                Device.close()
                print("🧹 GPIO resources cleaned up")
            except Exception as e:
                print(f"⚠️  Error during cleanup: {e}")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down gracefully...")
    sensor_hub.cleanup()
    client.stop()
    sys.exit(0)

# Set up signal handler
signal.signal(signal.SIGINT, signal_handler)

# Initialize Tendrl client
client = Client(
    mode="api",
    debug=True,
    max_batch_size=20,
    max_queue_size=200
)

client.start()

# Initialize sensor hub
sensor_hub = RaspberryPiSensorHub(simulation_mode=not GPIO_AVAILABLE)

print("🥧 Raspberry Pi IoT Sensor Hub Starting")
print(f"📍 Location: {LOCATION}")
print(f"🆔 Device ID: {DEVICE_ID}")
print(f"📊 Reading interval: {SENSOR_READ_INTERVAL} seconds")
print(f"⏱️  Simulation duration: {SIMULATION_DURATION} seconds")
print(f"🔧 Hardware mode: {'Real GPIO' if not sensor_hub.simulation_mode else 'Simulation'}")
print("📡 Press Ctrl+C to stop\n")

# Decorator for periodic environmental summary
@client.tether(tags=["environmental-summary", "raspberry-pi"])
def environmental_summary():
    """Generate periodic environmental summary"""
    return sensor_hub.get_environmental_summary()

# Decorator for device health check
@client.tether(tags=["device-health", "raspberry-pi"])
def device_health_check():
    """Check device health and status"""
    import psutil
    
    return {
        "device_health": {
            "device_id": DEVICE_ID,
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "temperature_cpu": psutil.sensors_temperatures().get('cpu_thermal', [{}])[0].get('current', None) if hasattr(psutil, 'sensors_temperatures') else None,
                "disk_usage_percent": psutil.disk_usage('/').percent
            },
            "gpio_status": "active" if not sensor_hub.simulation_mode else "simulated",
            "sensor_errors": len(sensor_hub.sensor_errors),
            "uptime_seconds": (datetime.utcnow() - sensor_hub.start_time).total_seconds()
        }
    }

# Main sensor reading loop
start_time = time.time()
reading_count = 0

try:
    while time.time() - start_time < SIMULATION_DURATION:
        cycle_start = time.time()
        
        # Collect sensor reading
        try:
            sensor_reading = sensor_hub.get_sensor_reading()
            client.publish(sensor_reading)
            reading_count += 1
            
            # Display current conditions
            temp = sensor_reading["sensors"]["temperature"]["value_celsius"]
            light = sensor_reading["sensors"]["light"]["value_percent"]
            motion = sensor_reading["sensors"]["motion"]["detected"]
            
            status_emoji = "🟢" if all(s["status"] == "ok" for s in sensor_reading["sensors"].values()) else "🟡"
            
            print(f"{status_emoji} Reading #{reading_count}: "
                  f"Temp: {temp}°C, Light: {light}%, Motion: {'Yes' if motion else 'No'}")
            
        except Exception as e:
            print(f"❌ Error reading sensors: {e}")
            if not sensor_hub.simulation_mode:
                try:
                    sensor_hub.error_led.on()
                    time.sleep(0.1)
                    sensor_hub.error_led.off()
                except:
                    pass
        
        # Environmental summary (every 6th reading)
        if reading_count % 6 == 0:
            try:
                environmental_summary()
                print("🌡️  Environmental summary generated")
            except Exception as e:
                print(f"❌ Error generating environmental summary: {e}")
        
        # Device health check (every 10th reading)
        if reading_count % 10 == 0:
            try:
                device_health_check()
                print("❤️  Device health check completed")
            except Exception as e:
                print(f"❌ Error in device health check: {e}")
        
        # Check for alerts
        if sensor_reading["sensors"]["temperature"]["value_celsius"]:
            temp = sensor_reading["sensors"]["temperature"]["value_celsius"]
            if temp > 30 or temp < 15:
                alert = {
                    "alert": {
                        "type": "temperature_extreme",
                        "severity": "warning",
                        "device_id": DEVICE_ID,
                        "message": f"Temperature outside normal range: {temp}°C",
                        "timestamp": datetime.utcnow().isoformat(),
                        "value": temp,
                        "threshold": "15-30°C"
                    }
                }
                client.publish(alert)
                print(f"🚨 Temperature alert: {temp}°C")
                
                # Sound buzzer if available
                if not sensor_hub.simulation_mode and sensor_hub.buzzer:
                    sensor_hub.buzzer.beep(0.5, 0.5, 3)
        
        # Wait for next reading
        cycle_duration = time.time() - cycle_start
        sleep_time = max(0, SENSOR_READ_INTERVAL - cycle_duration)
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            print(f"⚠️  Reading cycle took {cycle_duration:.2f}s "
                  f"(longer than {SENSOR_READ_INTERVAL}s interval)")

except KeyboardInterrupt:
    pass

print("\n✅ Sensor monitoring completed!")
print(f"📊 Total readings: {reading_count}")
print(f"🚶 Motion events: {sensor_hub.motion_events}")
print(f"🔘 Button presses: {sensor_hub.button_presses}")
print(f"❌ Sensor errors: {len(sensor_hub.sensor_errors)}")
print(f"⏱️  Total runtime: {time.time() - start_time:.1f} seconds")
print("🛑 Shutting down...")

# Cleanup
sensor_hub.cleanup()
client.stop() 