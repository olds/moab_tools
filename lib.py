from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont
import os, io, forecastio, config, pytz, urllib
from datetime import datetime, timezone
from boto3 import session

FONT_ALPHA = (255, 255, 255, 225)
FONT = ImageFont.truetype('Menlo-Bold.ttf', 16)


class Location:
    def __init__(self, resource_url, lat, lon, overlay_weather=True, overlay_title=False, title = None, overlay_time=True, prefix=None):
        self.resource_url = resource_url
        self.lat = lat
        self.lon = lon
        self.overlay_weather = overlay_weather
        self.prefix = prefix
        self.title = title
        self.overlay_title = overlay_title
        self.overlay_time = overlay_time
        self.weather_data = forecastio.load_forecast(config.DARKSKY_API_KEY, self.lat, self.lon, lazy=False)

    def fetch_raw_image(self):
        """
        Returns the image object for a particular location.
        :return: PIL Image
        """
        urlo = urlparse(self.resource_url)
        tmp_file = "/tmp/%s.png" % self.prefix
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)

        if urlo.scheme == 'rtsp':
            os.system('ffmpeg -rtsp_transport tcp -i "%s" -frames:v 1 -vsync 0 %s' % (self.resource_url, tmp_file))
            img = Image.open(tmp_file)

        else:
            img = Image.open(io.BytesIO(urllib.request.urlopen(self.resource_url).read()))

        return img


    def get_temp(self):
        temp = self.weather_data.currently().apparentTemperature
        f = round(float(temp), 1)
        c = (f - 32) * 5 / 9
        c = round(c, 1)

        return f, c

    def get_wind_speed(self):
        wind_speed_mph = int(float(self.weather_data.currently().windSpeed))

        wind_bearing = self.weather_data.currently().windBearing
        val = int((wind_bearing / 22.5) + .5)
        arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        wind_dir = arr[(val % 16)]

        return wind_speed_mph, wind_dir

    def get_timezone(self):
        location_timezone = pytz.timezone(self.weather_data.json['timezone'])
        return location_timezone

    def resize_image(self, img):
        if img.width > 1152:
            resized = img.resize((1152, 768), Image.LANCZOS)
        else:
            resized = img

        return resized

    def _get_overlay(self, size):
        overlay = Image.new('RGBA', size, (255, 255, 255, 0))
        return overlay

    def _overlay_title(self,img):
        img = img.convert('RGBA')
        # draw text, half opacity
        overlay = self._get_overlay(img.size)
        d = ImageDraw.Draw(overlay)
        cur_time = datetime.now(tz=self.get_timezone()).strftime("%Y-%m-%d %A %H:%M:%S")
        d.text((10, 10), cur_time, font=FONT, fill=FONT_ALPHA)
        out = Image.alpha_composite(img, overlay)
        return out

    def _overlay_time(self,img):
        img = img.convert('RGBA')
        # draw text, half opacity
        overlay = self._get_overlay(img.size)
        d = ImageDraw.Draw(overlay)
        d.text((img.width - 300, img.height - 20), self.title, font=FONT, fill=FONT_ALPHA)
        out = Image.alpha_composite(img, overlay)
        return out

    def _overlay_weather(self,img):
        img = img.convert('RGBA')

        f_temp, c_temp = self.get_temp()
        wind_speed, wind_dir = self.get_wind_speed()

        temp_str = str(f_temp) + "° F | " + str(c_temp) + "° C"
        wind_str = str(wind_speed) + " MPH " + wind_dir
        cur_time = datetime.now(tz=self.get_timezone()).strftime("%Y-%m-%d %A %H:%M:%S")

        weather_overlay = self._get_overlay(img.size)
        # get a drawing context
        d = ImageDraw.Draw(weather_overlay)
        # draw text, half opacity
        d.text((img.width - 300, img.height - 60), temp_str, font=FONT, fill=FONT_ALPHA)
        d.text((img.width - 300, img.height - 40), wind_str, font=FONT, fill=FONT_ALPHA)
        # draw text, full opacity
        out = Image.alpha_composite(img, weather_overlay)

        return out

    def get_latest_image(self):
        img = self.resize_image(self.fetch_raw_image())

        if self.overlay_weather:
            img = self._overlay_weather(img)

        if self.overlay_title:
            img = self._overlay_title(img)

        if self.overlay_time:
            img = self._overlay_time(img)

        return img

    def save_image(self, img):

        tmp_file = "/tmp/%s.png" % self.prefix
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        img.save(tmp_file)

        bsession = session.Session()
        client = bsession.client('s3',
                                region_name='sfo2',
                                endpoint_url='https://moab.sfo2.digitaloceanspaces.com',
                                aws_access_key_id=config.ACCESS_ID,
                                aws_secret_access_key=config.SECRET_KEY)

        client.upload_file(Filename=tmp_file,
                           Bucket='moab',
                           Key='%s/%s' % (self.get_foldername(), self.get_filename()),
                           ExtraArgs={'ACL': 'public-read'})

    def get_image_tag(self):
        sunrise = self.weather_data.daily().data[0].sunriseTime.replace(tzinfo=timezone.utc).astimezone(tz=self.get_timezone())
        sunset = self.weather_data.daily().data[0].sunsetTime.replace(tzinfo=timezone.utc).astimezone(tz=self.get_timezone())

        u = datetime.now(tz=self.get_timezone())

        sunrise_diff = sunrise - u
        sunrise_diff_min = sunrise_diff.total_seconds() / 60

        sunset_diff = sunset - u
        sunset_diff_min = sunset_diff.total_seconds() / 60

        if abs(sunrise_diff_min) < 40:
            tag = 'sunrise'
        elif sunset_diff_min > 0 and sunset_diff_min < 40:
            tag = 'sunset'
        elif sunset_diff_min < 0 and abs(sunset_diff_min) < 40:
            tag = 'dusk'
        elif sunrise_diff_min < 0 and sunset_diff_min < 0:
            tag = 'night'
        elif sunrise_diff_min > 0 and sunset_diff_min > 0:
            tag = 'night'
        else:
            tag = 'day'

        return tag

    def get_filename(self):
        current_time_str = datetime.now(tz=self.get_timezone()).strftime('%Y-%m-%d_%H-%M-%S')
        return "%s_%s_%s.png" % (self.prefix, current_time_str, self.get_image_tag())

    def get_foldername(self):
        current_date_str = datetime.now(tz=self.get_timezone()).strftime('%Y-%m-%d')
        return "%s_%s" % (self.prefix, current_date_str)

    def process(self):
        img = self.get_latest_image()
        self.save_image(img)