#!/usr/bin/env python3

try: 
    import OPi.GPIO as GPIO
    GPIO.setboard(GPIO.PRIME)       # Orange Pi PC board
    GPIO.setmode(GPIO.BOARD)        # set up BOARD BCM numbering
    GPIO.setwarnings(True)          # Turn warnings on/off 
except:
    print("Error importing the GPIO lib, exit")
    exit(1)

# Pins estilo BCM
PIN_FANCONTROL  = 7
PIN_DHT11       = 35

#
import dht11
import time
import datetime
# 
from timeloop import Timeloop
from datetime import timedelta
from influxdb import InfluxDBClient
from math import sqrt

# timeloop instance
tl = Timeloop()
INTERVAL_MEASURE = 30
INTERVAL_PUSH = 300

## vars
cpu_temp = 0.0
gpu_temp = 0.0
fanspeed = 0
dht_temp = 0.0
dht_hum  = 0.0
dht_feel = 0.0
valid_data = False

#### GPIO general related
def cleanup():
    if pwm != False:
        pwm.stop()

    # close the GPIO
    GPIO.cleanup()

    # stop the TL
    tl.stop()


#### TEMP related
cpupath = "/sys/class/thermal/thermal_zone0/temp"
gpupath = "/sys/class/thermal/thermal_zone1/temp"

def _temp(file):
    with open(file) as cpud:
        return int(cpud.readline())/1000.0

def cpu():
    return _temp(cpupath)

def gpu():
    return _temp(gpupath)


#### FAN related
PWM_FREQ = 1000
GPIO.setup(PIN_FANCONTROL, GPIO.OUT)
pwm = GPIO.PWM(PIN_FANCONTROL, PWM_FREQ)
pwm.ChangeDutyCycle(0)
pwm.start(1)


def set_fanspeed(speed):
    if speed > 100:
        speed = 100
    
    if speed < 0:
        speed = 0

    pwm.ChangeDutyCycle(speed)
    fanspeed = speed

def fanoff():
    fanspeed(0)


#### DHT11 related
dht = dht11.DHT11(pin=PIN_DHT11)

def get_dht_data():
    result = dht.read()
    if result.is_valid():
        return (result.temperature, result.humidity)
    else:
        return (dht_temp, dht_hum)

def toFahrenheit(celcius):
    return 1.8 * celcius + 32.0

def toCelsius(fahrenheit):
    return (fahrenheit - 32.0) / 1.8

def get_dht_temp_feel(temperature, percentHumidity):
    # Using both Rothfusz and Steadman's equations
    # http://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    hi = 0
    T = toFahrenheit(temperature)
    T2 = T**2
    H = percentHumidity
    H2 = H**2

    hi = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (H * 0.094))

    if (hi > 79):
        hi = -42.379 + 2.04901523 * T + 10.14333127 * H + -0.22475541 * T * H + -0.00683783 * T2 + -0.05481717 * H2 + 0.00122874 * T2 * H + 0.00085282 * T * H2 + -0.00000199 * T2 * H2

        if ((H < 13) and (T >= 80.0) and (T <= 112.0)):
            hi -= ((13.0 - H) * 0.25) * sqrt((17.0 - abs(T - 95.0)) * 0.05882)

        elif ((H > 85.0) and (T >= 80.0) and (T <= 87.0)):
            hi += ((H - 85.0) * 0.1) * ((87.0 - T) * 0.2)

    C = toCelsius(hi)
    return C


#### influxdb related
idb_host = "localhost"
idb_port = 8086
idb_database = "test"
idb_client = InfluxDBClient(host=idb_host, port=idb_port, database=idb_database)


#### time paced funcions
#@tl.job(interval=timedelta(seconds=INTERVAL_MEASURE))
def show_vars():
    global cpu_temp, gpu_temp, dht_temp, dht_hum, dht_feel
    print("")
    print("======================================")
    print("CPU temp: {} celcius".format(cpu_temp))
    print("GPU temp: {} celcius".format(gpu_temp))
    print("Room temp: {} celcius".format(dht_temp))
    print("Room hum: {} %".format(dht_hum))
    print("Room temp {} vs feel {}".format(dht_temp, dht_feel))

@tl.job(interval=timedelta(seconds=INTERVAL_MEASURE))
def update_vars():
    global cpu_temp, gpu_temp, dht_hum, dht_temp, dht_feel, valid_data

    cpu_temp = cpu()
    gpu_temp = gpu()
    dht_temp, dht_hum = get_dht_data()
    dht_feel = get_dht_temp_feel(dht_temp, dht_hum)
    if dht_temp > 10 and dht_hum > 10 and dht_feel > 10:
        valid_data = True

@tl.job(interval=timedelta(seconds=INTERVAL_PUSH))
def influx_insert():
    global dht_temp, dht_hum, dht_hum, idb_client, idb_database
    
    if valid_data:
        data = []
        data.append(
            {
                "measurement": "temperature",
                "tags": {
                    "device": "OPi", 
                    "sensor": "DHT11", 
                    "place": "Hab",
                    "comment": "real"},
                "fields": {"value": dht_temp}
            })

        data.append(
            {
                "measurement": "humidity",
                "tags": {
                    "device": "OPi", 
                    "sensor": "DHT11", 
                    "place": "Hab",
                    "comment": "real"},
                "fields": {"value": dht_hum}
            })

        data.append(
            {
                "measurement": "temperature",
                "tags": {
                    "device": "OPi", 
                    "sensor": "DHT11", 
                    "place": "Hab",
                    "comment": "feel"},
                "fields": {"value": dht_feel}
            })

        idb_client.write_points(data)


if __name__ == '__main__':
    try:
        # start the time loops
        tl.start()

        while True:
            time.sleep(1)
    
    except:
        print("Cleanup")
        cleanup()
