#!/bin/bash
cd /home/ubuntu/

current_date=`date '+%Y-%m-%d'`

mkdir $current_date
cd $current_date

s3cmd get --exclude "*night*" --exclude "*.mp4" --exclude "*.webm" s3://moab.sherlocklabs.io/$current_date/* .
find . -type f -size 0b -delete
python /home/ubuntu/get_image_file_list.py 24 $1 | grep 'dusk\|sunset' > last_sunset.txt
python /home/ubuntu/get_image_file_list.py 48 $1 | grep 'day\|sunrise\|sunset\|dusk' > last_day.txt

# sunset
ffmpeg -r 6 -safe 0 -f concat -i last_sunset.txt -vf scale=972:720 -threads 4 -c:v libx264 -preset fast -r 6 -crf 10 -b:v 0 -y sunset_$current_date.mp4
s3cmd put --acl-public sunset_$current_date.mp4 s3://moab.sherlocklabs.io/$current_date/sunset_$current_date.mp4

ffmpeg -r 30 -safe 0 -f concat -i last_day.txt -vf scale=972:720 -threads 4 -c:v libx264 -preset fast -r 30 -crf 10 -b:v 0 -y day_$current_date.mp4
s3cmd put --acl-public day_$current_date.mp4 s3://moab.sherlocklabs.io/$current_date/day_$current_date.mp4

#webm goes here becomes it is slow
ffmpeg -r 6 -safe 0 -f concat -i last_sunset.txt -vf scale=972:720 -threads 4 -c:v libvpx-vp9 -r 6 -crf 10 -b:v 0 -y sunset_$current_date.webm
s3cmd put --acl-public sunset_$current_date.webm s3://moab.sherlocklabs.io/$current_date/sunset_$current_date.webm

ffmpeg -r 30 -safe 0 -f concat -i last_day.txt -vf scale=972:720 -threads 4 -c:v libvpx-vp9 -r 30 -crf 10 -b:v 0 -y day_$current_date.webm
s3cmd put --acl-public day_$current_date.webm s3://moab.sherlocklabs.io/$current_date/day_$current_date.webm

cd /home/ubuntu

sed "s/__date__/$current_date/g" index_template.html > index.html
s3cmd put --acl-public --add-header="Cache-Control:max-age=3600" index.html s3://moab.sherlocklabs.io/

rm -rf $current_date