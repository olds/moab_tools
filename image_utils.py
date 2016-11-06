# -*- coding: utf-8 -*-
import requests, sys, json
import requests_cache
import hashlib
import config
from datetime import datetime
import urllib, json, pytz, dateutil.parser, time
from wand.image import Image
from wand.display import display
from wand.drawing import Drawing
from wand.color import Color


def degToCompass(num):
    val=int((num/22.5)+.5)
    arr=["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return arr[(val % 16)]

def get_weather_data(prefix, lat, lon):
    cache_name = "%s_weather" % prefix
    requests_cache.install_cache(cache_name=cache_name, backend='sqlite', expire_after=180)
    url = "https://api.darksky.net/forecast/%s/%s,%s" % (config.DARKSKY_API_KEY, lat, lon)
    r = requests.get(url)
    data = r.json()

    return data

def get_temp(prefix, lat, lon):
    data = get_weather_data(prefix, lat, lon)
    f = round(float(data['currently']['apparentTemperature']),1)
    c = (f - 32) * 5/9
    c = round(c,1)

    return (f, c)

def get_wind(prefix, lat, lon):
    data = get_weather_data(prefix, lat, lon)
    wind_speed_mph = int(float(data['currently']['windSpeed']))
    wind_dir = degToCompass(data['currently']['windBearing'])

    return (wind_speed_mph, wind_dir)

def get_image_tag(prefix, lat, lon):
    location_data = get_weather_data(prefix, lat, lon)
    location_timezone = pytz.timezone(location_data['timezone'])
    sunrise = datetime.fromtimestamp(location_data['daily']['data']['sunriseTime'], tz=location_timezone)
    sunset = datetime.fromtimestamp(location_data['daily']['data']['sunsetTime'], tz=location_timezone)

    u = datetime.now(tz=location_timezone)

    sunrise_diff = sunrise - u
    sunrise_diff_min = sunrise_diff.total_seconds()/60

    sunset_diff = sunset - u
    sunset_diff_min = sunset_diff.total_seconds()/60

    if abs(sunrise_diff_min) < 40:
        tag = 'sunrise'
    elif sunset_diff_min > 0 and sunset_diff_min < 40:
        tag = 'sunset'
    elif sunset_diff_min < 0 and abs(sunset_diff_min) < 40:
        tag = 'dusk'
    elif sunrise_diff_min < 0 and sunset_diff_min <0:
        tag = 'night'
    elif sunrise_diff_min > 0 and sunset_diff_min >0:
        tag = 'night'
    else:
        tag = 'day'

    return tag

def create_filename(prefix, lat, lon):
    current_time_str = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
    tag = get_image_tag(prefix, lat, lon)
    return "%s_%s_%s" % (prefix, current_time_str, tag)

def fetch_original_image(url, prefix):
    urllib.urlretrieve(url, hashlib.md5(create_filename(prefix)))

def overlay_weather(prefix):
    temp_data = get_temp()
    wind_data = get_wind()
    output_filename = create_filename(prefix)
    
    temp_str = str(temp_data[0])+"° F | "+str(temp_data[1])+ "° C"
    wind_str = str(wind_data[0])+" MPH "+wind_data[1]

    with Image(filename=hashlib.md5(output_filename)) as img:
        with Drawing() as draw:
            draw.fill_color=Color('#292929')
            draw.fill_opacity = 0.2
            draw.rectangle(left=30, top=1810, width=340, height=100)
            draw.draw(img)
            draw.fontfamily = 'CourierNew'
            draw.font_size = 42
            draw.fill_color = Color('White')
            draw.gravity = 'south_west'
            draw.text(30,17,wind_str)
            draw.text(30,60,temp_str)
            draw.draw(img)
            img.save(filename=create_filename)

def process_image(location_config):
    fetch_original_image(location_config['url'], location_config['prefix'])
    overlay_weather(location_config['prefix'], location_config['lat'], location_config['lon'])
