Usage:
```
python3 tigo.py --mqtt-broker "192.168.1.100" --mqtt-port 1884 --mqtt-user "myuser" --mqtt-pass "mypassword" --tigo-router "10.11.1.212" --poll-interval 15 -debug
```


--mqtt-broker: MQTT broker address (default: 192.168.1.250)

--mqtt-port: MQTT broker port (default: 1883)

--mqtt-user: MQTT username (default: '')

--mqtt-pass: MQTT password (default: '')

--tigo-router: Tigo router IP address (default: 10.11.1.211)

--poll-interval: Time in seconds between each poll/publish cycle (default: 10 seconds)

-debug: enables verbose logging in the commandline
