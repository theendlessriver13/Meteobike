# -*- coding: utf-8 -*-
"""
Program <crowdbike.py> to read and record GPS data,
air temperature and humidity
using Adafruit's Ultimate GPS and a DHT22 temperature sensor while riding
on a bike.

First established at:
    University of Freiburg
    Environmental Meteology
    Version 1.2
    Written by Heinz Christen Mar 2018
    Modified by Andreas Christen Apr 2018
    https://github.com/achristen/Meteobike

Modified Apr 2020:
    Ruhr-University Bochum
    Urban Climatology Group
    Jonas Kittner
    added a nova PM-sensor to the kit
    made a non-GUI version to run in background
    reworked all internals - using adafruit blinka circuitpython library
"""
import csv
import datetime
import json
import os
import signal
import time

import adafruit_dht
import board
import numpy as np
from FUN import get_wlan_macaddr
from FUN import GPS
from FUN import pm_sensor
from FUN import read_dht22
from FUN import sat_vappressure
from FUN import vappressure

# __load config files__
with open(
    os.path.join(
        os.path.dirname(__file__),
        'config.json',
    ), 'r',
) as config:
    config = json.load(config)

raspberryid = config['user']['bike_nr']  # number of your pi
studentname = config['user']['studentname']
mac = get_wlan_macaddr()

with open(
    os.path.join(
        os.path.dirname(__file__),
        'calibration.json',
    ), 'r',
) as calib:
    calib = json.load(calib)

# __calibration params__
temperature_cal_a1 = calib['temp_cal_a1']
temperature_cal_a0 = calib['temp_cal_a0']
hum_cal_a1 = calib['hum_cal_a1']
hum_cal_a0 = calib['hum_cal_a0']

logfile_path = config['user']['logfile_path']
if not os.path.exists(logfile_path):
    os.makedirs(logfile_path)
logfile_name = f'{raspberryid}_{studentname}_{datetime.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")}.csv'  # noqa E501
logfile = os.path.join(logfile_path, logfile_name)


columnnames = [
    'id',
    'record',
    'raspberry_time',
    'gps_time',
    'altitude',
    'latitude',
    'longitude',
    'speed',
    'temperature',
    'temperature_raw',
    'rel_humidity',
    'rel_humidity_raw',
    'vapour_pressure',
    'pm10',
    'pm2_5',
    'mac',
]

# check if file is already there
if not os.path.exists(logfile):
    f = open(logfile, 'a', newline='')
    writer = csv.DictWriter(f, columnnames)
    writer.writeheader()
    f.close()

# __global variables___
counter = 1
pm_status = config['user']['pm_sensor']
sampling_rate = config['user']['sampling_rate']


def exit_program(signum, frame) -> None:
    global f
    gpsp.running = False
    gpsp.stop()
    gpsp.join()
    try:
        f.close()
    except Exception:
        pass

    exit(0)


gpsp = GPS()
gpsp.start()
dht22_sensor = adafruit_dht.DHT22(board.D4)
nova_pm = pm_sensor(dev='/dev/ttyUSB0')


def main() -> None:
    global counter
    while True:
        now = datetime.datetime.utcnow()
        if gpsp.has_fix:
            f = open(logfile, 'a', newline='')
            writer = csv.DictWriter(f, columnnames)

            # get sensor readings from DHT-sensor
            try:
                readings = read_dht22(dht22_sensor)
            except Exception:
                dht22_humidity = np.nan
                dht22_temperature = np.nan

            dht22_humidity = readings['humidity']
            dht22_temperature = readings['temperature']

            # calculate temperature with sensor calibration values
            dht22_temperature_raw = round(dht22_temperature, 5)
            dht22_temperature_calib = round(
                dht22_temperature /
                temperature_cal_a1 -
                temperature_cal_a0, 3,
            )

            dht22_humidity_raw = round(dht22_humidity, 5)
            dht22_humidity_calib = round(
                dht22_humidity /
                hum_cal_a1 -
                hum_cal_a0, 3,
            )

            saturation_vappress = sat_vappressure(dht22_temperature_calib)
            dht22_vappress = round(
                vappressure(
                    dht22_humidity_calib,
                    saturation_vappress,
                ), 5,
            )

            # read pm-sensor takes max 1 sec
            if pm_status is True:
                pm = nova_pm.read_pm()
                pm2_5 = pm['PM2_5']
                pm10 = pm['PM10']
            else:
                pm2_5 = np.nan
                pm10 = np.nan

            if dht22_humidity > 100:
                dht22_humidity = 100

            # Get GPS position
            gps_time = gpsp.timestamp
            gps_altitude = gpsp.alt
            gps_latitude = gpsp.latitude
            gps_longitude = gpsp.longitude
            gps_speed = round(gpsp.speed * 1.852, 2)
            # convert to kph
            # f_mode = int(gpsd.fix.mode)  # store number of sats
            # has_fix = False  # assume no fix

            # build readings
            readings = {
                'id': raspberryid,
                'record': counter,
                'raspberry_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                'gps_time': gps_time,
                'altitude': gps_altitude,
                'latitude': gps_latitude,
                'longitude': gps_longitude,
                'speed': gps_speed,
                'temperature': dht22_temperature_calib,
                'temperature_raw': dht22_temperature_raw,
                'rel_humidity': dht22_humidity_calib,
                'rel_humidity_raw': dht22_humidity_raw,
                'vapour_pressure': dht22_vappress,
                'pm10': pm10,
                'pm2_5': pm2_5,
                'mac': mac,
            }

            # append to csv file
            writer.writerow(readings)
            f.close()

        finish = datetime.datetime.utcnow()
        runtime = finish - now
        offset = runtime.total_seconds()

        if offset > sampling_rate:
            offset = sampling_rate
        counter += 1

        time.sleep(sampling_rate - offset)


signal.signal(signal.SIGTERM, exit_program)

if __name__ == '__main__':
    main()
