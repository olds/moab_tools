from urllib.parse import urlparse
from PIL import Image, ImageDraw
import os, io, forecastio, config, pytz, urllib, shutil, ffmpeg, mimetypes, time, moabim.utils as utils
from datetime import datetime, timezone
from boto3 import session
from aws_requests_auth.aws_auth import AWSRequestsAuth
from concurrent.futures import ThreadPoolExecutor
from requests_futures.sessions import FuturesSession


class Location:
    def __init__(self, resource_url, lat, lon, overlay_weather=True, overlay_title=False, title=None,
                 overlay_time=True, prefix=None, frequency=1):
        self.resource_url = resource_url
        self.lat = lat
        self.lon = lon
        self.overlay_weather = overlay_weather
        self.prefix = prefix
        self.title = title
        self.overlay_title = overlay_title
        self.overlay_time = overlay_time
        self.frequency = frequency
        self.weather_data = forecastio.load_forecast(config.DARKSKY_API_KEY, self.lat, self.lon, lazy=False)

    def _get_spaces_session(self):
        bsession = session.Session()
        client = bsession.client('s3',
                                 region_name=config.S3_REGION,
                                 endpoint_url='https://%s.%s' % (config.S3_REGION, config.S3_ENDPOINT),
                                 aws_access_key_id=config.ACCESS_ID,
                                 aws_secret_access_key=config.SECRET_KEY)

        return client

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
            (
                ffmpeg
                    .input(self.resource_url, rtsp_transport='tcp')
                    .output(tmp_file, **{'frames:v': 1, 'vsync': 0})
                    .run()
            )
            img = Image.open(tmp_file)

        else:
            img = Image.open(io.BytesIO(urllib.request.urlopen(self.resource_url).read()))

        return img

    def get_temp(self):
        """
        Returns a tuple of the current temperature in F and C
        :return: tuple (f, c)
        """
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
        # target 720p image size
        if img.width > 1280:
            new_height = int((1280/img.width) * img.height)
            resized = img.resize((1280, new_height), Image.LANCZOS)
        else:
            resized = img

        return resized

    def _get_overlay(self, size):
        overlay = Image.new('RGBA', size, (255, 255, 255, 0))
        return overlay

    def _overlay_time(self, img):
        img = img.convert('RGBA')
        # draw text, half opacity
        overlay = self._get_overlay(img.size)
        d = ImageDraw.Draw(overlay)
        cur_time = datetime.now(tz=self.get_timezone()).strftime("%Y-%m-%d %A %H:%M:%S")
        d.text((10, 10), cur_time, font=config.FONT, fill=config.FONT_ALPHA)
        out = Image.alpha_composite(img, overlay)
        return out

    def _overlay_title(self, img):
        img = img.convert('RGBA')
        # draw text, half opacity
        overlay = self._get_overlay(img.size)
        d = ImageDraw.Draw(overlay)
        d.text((img.width - 300, img.height - 20), self.title, font=config.FONT, fill=config.FONT_ALPHA)
        out = Image.alpha_composite(img, overlay)
        return out

    def _overlay_weather(self, img):
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
        d.text((img.width - 300, img.height - 60), temp_str, font=config.FONT, fill=config.FONT_ALPHA)
        d.text((img.width - 300, img.height - 40), wind_str, font=config.FONT, fill=config.FONT_ALPHA)
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

    def get_latest_image_location(self):
        return 'https://%s.%s.%s/latest.png' % (self.prefix, config.S3_REGION, config.S3_ENDPOINT)

    def save_file_to_s3(self, file, key=None):
        if key is None:
            key = '%s/%s' % (self.get_foldername(), os.path.basename(file))
        client = self._get_spaces_session()
        client.upload_file(Filename=file,
                           Bucket=self.prefix,
                           Key=key,
                           ExtraArgs={'ACL': 'public-read',
                                      'ContentType': mimetypes.guess_type(file)[0],
                                      'ContentDisposition': 'inline',
                                      'CacheControl': 'max-age=0'})

    def save_image_to_file(self, img):
        tmp_file = "/tmp/%s" % self.get_current_image_filename()
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        img.save(tmp_file)
        self.save_file_to_s3(tmp_file)
        self.save_file_to_s3(tmp_file, 'latest.png')
        os.remove(tmp_file)

    def get_image_tag(self):
        sunrise = self.weather_data.daily().data[0].sunriseTime.replace(tzinfo=timezone.utc).astimezone(
            tz=self.get_timezone())
        sunset = self.weather_data.daily().data[0].sunsetTime.replace(tzinfo=timezone.utc).astimezone(
            tz=self.get_timezone())

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

    def get_current_image_filename(self):
        current_time_str = datetime.now(tz=self.get_timezone()).strftime('%Y-%m-%d_%H-%M-%S')
        return "%s_%s_%s.png" % (self.prefix, current_time_str, self.get_image_tag())

    def get_current_video_filename(self, suffix_tag=''):
        current_time_str = datetime.now(tz=self.get_timezone()).strftime('%Y-%m-%d')
        return "%s_%s_%s.mp4" % (self.prefix, current_time_str, suffix_tag)

    def get_foldername(self, date=None):
        if date:
            date_str = date
        else:
            date_str = datetime.now(tz=self.get_timezone()).strftime('%Y-%m-%d')
        return "%s_%s" % (self.prefix, date_str)

    def process(self):
        current_tag = self.get_image_tag()

        if current_tag == 'night' and datetime.now().minute % 30 != 0:
            return

        if datetime.now().minute % self.frequency != 0:
            return

        img = self.get_latest_image()
        self.save_image_to_file(img)

    def get_image_list(self, date, include_tags=None):
        image_list = self._get_spaces_session().list_objects(Bucket=self.prefix,
                                                             Prefix="%s_%s" % (self.prefix, date),
                                                             MaxKeys=3000)['Contents']

        image_files = []
        for v in image_list:
            image_filename = v['Key']

            if not include_tags or any(tag in image_filename for tag in include_tags):
                image_files.append(image_filename)

        image_files.sort()

        return image_files

    def download_image_list(self, date=None, tags_to_include=None):

        folder_path = "/tmp/%s/" % self.get_foldername(date)
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)

        image_list = self.get_image_list(date, tags_to_include)
        image_list.sort()

        # Only download files that aren't already downloaded
        files_to_download = [img for img in image_list if not
                             os.path.isfile('/tmp/%s/%s' % (folder_path, img.split("/")[1:][0]))]

        fsession = FuturesSession(executor=ThreadPoolExecutor(max_workers=20))
        auth = AWSRequestsAuth(aws_access_key=config.ACCESS_ID,
                               aws_secret_access_key=config.SECRET_KEY,
                               aws_host='%s.%s.%s' % (self.prefix, config.S3_REGION, config.S3_ENDPOINT),
                               aws_region=config.S3_REGION,
                               aws_service=self.prefix)

        _requests = []
        for img in files_to_download:
            r = fsession.get('https://%s.%s.%s/%s' % (self.prefix, config.S3_REGION, config.S3_ENDPOINT, img),
                             auth=auth,
                             background_callback=utils.save_to_file)
            _requests.append(r)

        for r in _requests:
            x = r.result()

        time.sleep(2)

        for k, img in enumerate(image_list):
            os.rename('/tmp/%s/%s' % (self.get_foldername(date), img.split("/")[1:][0]),
                      "/tmp/%s/image-%s.png" % (self.get_foldername(date), str(k).zfill(3)))

    def create_video(self, date, tags_to_include=None, duration=20, filename=None, video_type='mp4'):
        if tags_to_include is None:
            tags_to_include = ['sunrise', 'day', 'sunset', 'dusk']

        if filename is None:
            filename = '%s_%s.%s' % (self.prefix, date, video_type)

        self.download_image_list(date, tags_to_include)

        frame_count = len(self.get_image_list(date))
        frame_rate = int(frame_count/duration)

        folder_path = "/tmp/%s/" % (self.get_foldername(date))
        (
            ffmpeg
                .input("%simage-%%03d.png" % folder_path, pattern_type='sequence', framerate=frame_rate)
                .output('/tmp/%s' % filename)
                .run()
        )

        shutil.rmtree(path=folder_path, ignore_errors=True)

        self.save_file_to_s3('/tmp/%s' % filename, filename)
