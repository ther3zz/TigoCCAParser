#!/usr/bin/python3

import argparse
import requests
import time
import sys
import json
from datetime import datetime
from bs4 import BeautifulSoup
import paho.mqtt.client as mqtt

# Set up argument parser
parser = argparse.ArgumentParser(description="Tigo Solar Panel Data Publisher")
parser.add_argument('--device-name-prefix', default='Tigo Solar Panel', help='Prefix for device name in Home Assistant')
parser.add_argument('--device-model', default='Solar Panel', help='Model name for the device in Home Assistant')
parser.add_argument('--mqtt-broker', default='192.168.1.250', help='MQTT broker address')
parser.add_argument('--mqtt-port', type=int, default=1883, help='MQTT broker port')
parser.add_argument('--mqtt-user', default='', help='MQTT username')
parser.add_argument('--mqtt-pass', default='', help='MQTT password')
parser.add_argument('--tigo-router', default='10.11.1.211', help='Tigo router IP address')
parser.add_argument('--poll-interval', type=int, default=10, help='Time in seconds between each poll/publish cycle')
parser.add_argument('--topic-base', default='homeassistant/sensor/energy/tigo', help='Base MQTT topic for Home Assistant')
parser.add_argument('-debug', action='store_true', help='Enable debug mode')  # Add debug flag
args = parser.parse_args()

# Assign values from arguments
tigo_router = args.tigo_router
mqtt_broker = args.mqtt_broker
mqtt_port = args.mqtt_port
mqtt_user = args.mqtt_user
mqtt_pass = args.mqtt_pass
poll_interval = args.poll_interval
topic_base = args.topic_base

client_id = "tigo_energy_client"  # Unique client ID for MQTT connection

url = 'http://' + tigo_router + '/cgi-bin/mmdstatus'
session = requests.Session()
session.auth = ('Tigo', '$olar')

debug = args.debug  # Set debug flag based on CLI argument

mqttc = mqtt.Client(client_id=client_id, clean_session=False)  # Set client_id and disable clean session
mqttc.username_pw_set(mqtt_user, mqtt_pass)

# Enable detailed MQTT logging
mqttc.on_log = lambda client, userdata, level, buf: print(f"MQTT Log: {buf}")

if debug:
    print(f"Connecting to MQTT broker at {mqtt_broker}:{mqtt_port}...")

try:
    mqttc.connect(mqtt_broker, mqtt_port, keepalive=120)  # Set keepalive to 120 seconds
    mqttc.loop_start()
    if debug:
        print("MQTT connection established.")
except Exception as e:
    print(f"Failed to connect to MQTT broker: {e}")
    sys.exit(1)

def publish_discovery_message(sensor_id, unique_id, name, state_topic, unit_of_measurement, device_class, device):
    discovery_topic = f"homeassistant/sensor/{sensor_id}/config"
    discovery_payload = {
        "name": name,
        "unique_id": unique_id,  # Add unique ID for each sensor
        "state_topic": state_topic,
        "unit_of_measurement": unit_of_measurement,
        "device_class": device_class,
        "device": device  # Associate this sensor with a device
    }
    mqttc.publish(discovery_topic, json.dumps(discovery_payload))
    if debug:
        print(f"Published discovery message for {name} to {discovery_topic}: {json.dumps(discovery_payload)}")

def poll_tigo():
    try:
        response = session.get(url)
        if response.status_code == 200:
            html = response.content
            soup = BeautifulSoup(html, 'html.parser')  # Parse HTML 
            table = soup.find("table", {"class": "list_tb"})  # Data table in the center

            if table is None:
                if debug:
                    print("Data table not found in the HTML response.")
                return None

            rows = table.find_all('tr')
            d_ = {}
            d_['headline'] = ['Label', 'Barcode', 'MAC', 'Voltage_Vin', 'Voltage_Vin_%', 'Voltage_Vout', 'Voltage_Vout_%', 'Current_A', 'Power_W', 'Power_%', 'Temp_C', 'RSSI', 'BRSSI', 'Slot', 'VMPE', 'VMPE', 'Sync/Evt', 'Mode', 'Bypass', 'Event', 'Raw', 'Extra_Raw', 'Details_Raw']

            for row in rows:
                line = row.find_all('td')
                line = [e_.text.strip() for e_ in line]

                if debug:
                    print(f"Parsed line data: {line}")

                if len(line) > 10:
                    bc = line[0] + '___' + line[1]
                    d_[bc] = {}

                    for i in range(len(line)):
                        line[i] = line[i].replace('%', '')  # % is handled as float/int
                        line[i] = line[i].replace('\xa0', '_')  # Space 
                        line[i] = line[i].replace('on', '1')  # On binary, for Grafana display
                        line[i] = line[i].replace('off', '0')  # Off binary, for Grafana display
                        line[i] = line[i].replace('/', '-')  # Don't ask

                        try:
                            if '.' in line[i]:
                                d_[bc][d_['headline'][i]] = float(line[i])
                            else:
                                d_[bc][d_['headline'][i]] = int(line[i])
                        except Exception as e:
                            d_[bc][d_['headline'][i]] = line[i]

            # Remove 'headline' from the dictionary
            d_.pop('headline', None)

            if debug:
                print(f"Data parsed from Tigo (after removing 'headline'): {d_}")

            return d_

        else:
            if debug:
                print("Failed to connect to Tigo router, status code:", response.status_code)
            return None
    except Exception as e:
        if debug:
            print(f"Error polling Tigo: {e}")
        return None

def publish_mqtt(d_):
    if not isinstance(d_, dict):
        if debug:
            print("Data is not in the expected format (dictionary). Actual type:", type(d_))
        return

    # Send discovery messages for each solar panel
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
            unique_id = sensor_id  # Ensure each sensor has a unique ID
            name = f"{args.device_name_prefix} {panel_id} {metric}"
            state_topic = f"{topic_base}/{panel_id}/{metric}"
            unit_of_measurement = "W" if "Power_W" in metric else ("A" if "Current_A" in metric else ("V" if "Voltage" in metric else ""))
            device_class = "power" if "Power_W" in metric else ("current" if "Current_A" in metric else ("voltage" if "Voltage" in metric else ""))

            # Publish discovery message for each metric of each panel
            publish_discovery_message(
                sensor_id=sensor_id,
                unique_id=unique_id,
                name=name,
                state_topic=state_topic,
                unit_of_measurement=unit_of_measurement,
                device_class=device_class,
                device=device
            )

            # Publish the actual data to the respective topics
            if debug:
                print(f"Publishing to {state_topic}: {value}")

            if mqttc.is_connected():
                msg_info = mqttc.publish(state_topic, value)
                msg_info.wait_for_publish()
                if msg_info.rc != mqtt.MQTT_ERR_SUCCESS:
                    if debug:
                        print(f"Failed to publish to {state_topic}. Return code: {msg_info.rc}")
            else:
                if debug:
                    print("MQTT client is not connected. Skipping publish.")
                return

while True:
    if debug:
        print('Triggering data poll and publish...')
    d_ = poll_tigo()
    if d_:
        publish_mqtt(d_)
    else:
        if debug:
            print("No data to publish.")
    time.sleep(poll_interval)
