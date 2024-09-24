#!/usr/bin/python3
import re
import argparse
import requests
import time
import sys
import json
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import paho.mqtt.client as mqtt
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Set up argument parser
parser = argparse.ArgumentParser(description="Tigo CCA Data Publisher")
parser.add_argument('--device-name-prefix', default='Tigo Optimizer', help='Prefix for device name in Home Assistant')
parser.add_argument('--device-model', default='TS4-A-O', help='Model name for the device in Home Assistant')
parser.add_argument('--mqtt-broker', default='192.168.1.250', help='MQTT broker address')
parser.add_argument('--mqtt-port', type=int, default=1883, help='MQTT broker port')
parser.add_argument('--mqtt-user', default='', help='MQTT username')
parser.add_argument('--mqtt-pass', default='', help='MQTT password')
parser.add_argument('--tigo-router', default='10.11.1.211', help='Tigo router IP address')
parser.add_argument('--poll-interval', type=int, default=10, help='Time in seconds between each poll/publish cycle')
parser.add_argument('--topic-base', default='homeassistant/sensor/energy/tigo', help='Base MQTT topic for Home Assistant')
parser.add_argument('--log-file', default=None, help='Path to log file')  # New log-file argument
parser.add_argument('--timeout', type=int, default=5, help='Timeout in seconds for requests')  # New timeout argument
parser.add_argument('-debug', action='store_true', help='Enable debug mode')  # Add debug flag
args = parser.parse_args()

# Set up logging
log_level = logging.DEBUG if args.debug else logging.INFO
log_format = "%(asctime)s - %(levelname)s - %(message)s"

# Create logger
logger = logging.getLogger()
logger.setLevel(log_level)

# Create handlers
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
console_handler.setFormatter(logging.Formatter(log_format))

logger.addHandler(console_handler)

if args.log_file:
    file_handler = logging.FileHandler(args.log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)

# Assign values from arguments
tigo_router = args.tigo_router
mqtt_broker = args.mqtt_broker
mqtt_port = args.mqtt_port
mqtt_user = args.mqtt_user
mqtt_pass = args.mqtt_pass
poll_interval = args.poll_interval
topic_base = args.topic_base
timeout = args.timeout  # Assign the timeout from the arguments

client_id = "tigo_energy_client"  # Unique client ID for MQTT connection

url = 'http://' + tigo_router + '/cgi-bin/mmdstatus'
# Create session and set basic auth
session = requests.Session()
session.auth = ('Tigo', '$olar')

# Set up retries and keep-alive to prevent dropped connections
retry_strategy = Retry(
    total=3,  # Number of retries before giving up
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP status codes
    method_whitelist=["HEAD", "GET", "OPTIONS"],  # Retry on specific HTTP methods
    backoff_factor=0.3  # Exponential backoff factor (0.3, 0.6, 1.2, etc.)
)
adapter = HTTPAdapter(max_retries=retry_strategy)

# Mount adapter to the session
session.mount("http://", adapter)
session.mount("https://", adapter)

# Optional: TCP keep-alive
session.keep_alive = True


mqttc = mqtt.Client(client_id=client_id, clean_session=False)  # Set client_id and disable clean session
mqttc.username_pw_set(mqtt_user, mqtt_pass)

# Enable detailed MQTT logging
mqttc.on_log = lambda client, userdata, level, buf: logger.debug(f"MQTT Log: {buf}")

logger.debug(f"Connecting to MQTT broker at {mqtt_broker}:{mqtt_port}...")

try:
    mqttc.connect(mqtt_broker, mqtt_port, keepalive=120)  # Set keepalive to 120 seconds
    mqttc.loop_start()
    logger.info("MQTT connection established.")
except Exception as e:
    logger.error(f"Failed to connect to MQTT broker: {e}")
    sys.exit(1)

def publish_discovery_message(sensor_id, unique_id, name, state_topic, unit_of_measurement, device_class, device):
    sanitized_sensor_id = re.sub(r'[^a-zA-Z0-9-_]', '_', sensor_id)
    discovery_topic = f"homeassistant/sensor/{sanitized_sensor_id}/config"
    
    discovery_payload = {
        "name": name,
        "unique_id": unique_id,  
        "state_topic": state_topic,
        "unit_of_measurement": unit_of_measurement,
        "device_class": device_class,
        "device": device  
    }
    mqttc.publish(discovery_topic, json.dumps(discovery_payload))
    logger.debug(f"Published discovery message for {name} to {discovery_topic}: {json.dumps(discovery_payload)}")

def poll_tigo():
    try:
        response = session.get(url, timeout=timeout)  # Use the timeout argument here
        if response.status_code == 200:
            html = response.content
            soup = BeautifulSoup(html, 'html.parser')  
            table = soup.find("table", {"class": "list_tb"})  

            if table is None:
                logger.debug("Data table not found in the HTML response.")
                return None

            rows = table.find_all('tr')
            d_ = {}
            d_['headline'] = ['Label', 'Barcode', 'MAC', 'Voltage_Vin', 'Voltage_Vin_%', 'Voltage_Vout', 'Voltage_Vout_%', 'Current_A', 'Power_W', 'Power_%', 'Temp_C', 'RSSI', 'BRSSI', 'Slot', 'VMPE', 'VMPE', 'Sync/Evt', 'Mode', 'Bypass', 'Event', 'Raw', 'Extra_Raw', 'Details_Raw']

            for row in rows:
                line = row.find_all('td')
                line = [e_.text.strip() for e_ in line]

                logger.debug(f"Parsed line data: {line}")

                if len(line) > 10:
                    bc = line[0] + '___' + line[1]
                    d_[bc] = {}

                    for i in range(len(line)):
                        line[i] = line[i].replace('%', '')  
                        line[i] = line[i].replace('\xa0', '_')  
                        line[i] = line[i].replace('on', '1')  
                        line[i] = line[i].replace('off', '0')  
                        line[i] = line[i].replace('/', '-')  

                        try:
                            if '.' in line[i]:
                                d_[bc][d_['headline'][i]] = float(line[i])
                            else:
                                d_[bc][d_['headline'][i]] = int(line[i])
                        except Exception as e:
                            d_[bc][d_['headline'][i]] = line[i]

            d_.pop('headline', None)

            logger.debug(f"Data parsed from Tigo (after removing 'headline'): {d_}")

            return d_

        else:
            logger.debug(f"Failed to connect to Tigo router, status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error polling Tigo: {e}")
        return None

def publish_mqtt(d_):
    if not isinstance(d_, dict):
        logger.debug(f"Data is not in the expected format (dictionary). Actual type: {type(d_)}")
        return

    for panel_id, panel_data in d_.items():
        sensor_id_base = f"energy_tigo_{panel_id.replace('___', '_')}"
        device = {
            "identifiers": [sensor_id_base],
            "name": f"{args.device_name_prefix} {panel_id}",
            "manufacturer": "Tigo",
            "model": args.device_model
        }
        for metric, value in panel_data.items():
            sensor_id = f"{sensor_id_base}_{metric}"
            unique_id = sensor_id  
            name = f"{args.device_name_prefix} {panel_id} {metric}"
            state_topic = f"{topic_base}/{panel_id}/{metric}"
            
            unit_of_measurement = ""
            device_class = None

            if "Power_W" in metric:
                unit_of_measurement = "W"
                device_class = "power"
            elif "Current_A" in metric:
                unit_of_measurement = "A"
                device_class = "current"
            elif "Voltage" in metric:
                unit_of_measurement = "V"
                device_class = "voltage"
            elif "Temp_C" in metric:
                unit_of_measurement = "°C"
                device_class = "temperature"
            elif "RSSI" in metric:
                unit_of_measurement = "dBm"
                device_class = "signal_strength"
            elif "Bypass" in metric or "Event" in metric or "Raw" in metric:
                device_class = "enum"  
            
            if isinstance(value, str) and value == 'n-a':
                logger.debug(f"Non-numeric value for {metric}: {value}. Replacing with None.")
                value = None  

            publish_discovery_message(
                sensor_id=sensor_id,
                unique_id=unique_id,
                name=name,
                state_topic=state_topic,
                unit_of_measurement=unit_of_measurement,
                device_class=device_class if device_class else None,
                device=device
            )

            logger.debug(f"Publishing to {state_topic}: {value}")

            if mqttc.is_connected():
                if value is not None:
                    msg_info = mqttc.publish(state_topic, value)
                    msg_info.wait_for_publish()
                    if msg_info.rc != mqtt.MQTT_ERR_SUCCESS:
                        logger.debug(f"Failed to publish to {state_topic}. Return code: {msg_info.rc}")
                else:
                    logger.debug(f"Skipping publishing None value to {state_topic}.")
            else:
                logger.error("MQTT client is not connected. Skipping publish.")
                return


next_poll_time = datetime.now()

while True:
    current_time = datetime.now()

    if current_time >= next_poll_time:
        logger.debug('Triggering data poll and publish...')
        
        # Measure the start time of polling and publishing
        start_time = datetime.now()

        # Poll and publish the data
        d_ = poll_tigo()
        if d_:
            publish_mqtt(d_)
        else:
            logger.debug("No data to publish.")

        # Measure the time taken for polling and publishing
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        # Adjust the next poll time based on the original cycle duration
        if processing_time >= poll_interval:
            logger.warning(f"Processing time ({processing_time}s) exceeded poll interval. Scheduling next poll immediately.")
            next_poll_time = datetime.now()  # Start immediately if processing exceeds interval
        else:
            # Set the next poll time by adding the poll_interval, subtracting the processing time
            next_poll_time += timedelta(seconds=(poll_interval - processing_time))

    # Calculate dynamic sleep time based on remaining time until next poll
    sleep_time = max(0.5, (next_poll_time - datetime.now()).total_seconds())
    time.sleep(sleep_time)
