from config import IMAGE_LOCATIONS
import datetime

yesterday = datetime.date.today() - datetime.timedelta(days = 1)

for location in IMAGE_LOCATIONS:
    location.create_video(date=str(yesterday))