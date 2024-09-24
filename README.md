I took the idea from the following post and modified things to work with home assistant:
[https://www.photovoltaikforum.com/](https://www.photovoltaikforum.com/thread/149592-details-protokolle-zugang-auf-tigo-cca/?postID=3929749#post3929749)


I'm currently running this script via docker (using a debian bookworm image)

### Command-Line Arguments

- `--mqtt-broker`:  
  MQTT broker address  
  **default**: `192.168.1.250`

- `--mqtt-port`:  
  MQTT broker port  
  **default**: `1883`

- `--mqtt-user`:  
  MQTT username  
  **default**: ``

- `--mqtt-pass`:  
  MQTT password  
  **default**: ``

- `--topic-base`:  
  Sets the base MQTT topic.  
  **default**: `homeassistant/sensor/energy/tigo`

- `--tigo-router`:  
  Tigo router IP address  
  **default**: `10.11.1.211`

- `--device-name-prefix`:  
  Sets the prefix of the device name in Home Assistant  
  **default**: `Tigo Optimizer`

- `--device-model`:  
  Model name for the device in Home Assistant  
  **default**: `TS4-A-O`

- `--poll-interval`:  
  Time in seconds between each poll/publish cycle  
  **default**: `10 seconds`

- `--timeout`:  
  Timeout in seconds for requests to the Tigo router  
  **default**: `5 seconds`

- `--log-file`:  
  Path to the log file  
  **default**: `None`

- `-debug`:  
  Enables verbose logging in the command line

### Example usage:
```bash
python script.py --mqtt-broker 192.168.1.50 --mqtt-port 1884 --mqtt-user myuser --mqtt-pass mypassword --poll-interval 10 --timeout 20 --log-file /path/to/logfile -debug
