from flask import Flask, render_template
import config
app = Flask(__name__, subdomain_matching=True)
app.config['SERVER_NAME'] = "sherlocklabs.local:5000"
app.url_map.default_subdomain = "www"


@app.route('/', subdomain="<site>")
def hello_world(site=None):
    j = None
    for x in config.IMAGE_LOCATIONS:
        if site == x.prefix:
            j = x

    print(site)

    return render_template('index.html', image_url=j.get_latest_image_location())