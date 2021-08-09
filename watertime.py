from flask import Flask, request, Response
import grohe_api, grohe_bt
import time
from flask_apscheduler import APScheduler
import logging
import logging.handlers
import yaml

# load config
with open('config.yaml', 'r') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

# set up logging
from logging.config import dictConfig

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': config['log_file'],
        'formatter': 'default',
        'maxBytes' : 2**20,
        'backupCount' : 3
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

# do main flask init
app = Flask(__name__)         
logger = app.logger

# start flask task scheduler
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Login to Grohe cloud infra to get parameters
logger.info("Logging into Grohe cloud to get user id and key...")
gapi = grohe_api.GroheApi()
gapi.login(config['user'], config['password'])
gapi.read_dashboard()
user_id = gapi.user_id
presharedkey = gapi.presharedkey
logger.info("Got user id: %s and PSK: %s" %(user_id, presharedkey))

# Find BT device and resolve GATT characteristic
logger.info("Connecting to BT device...")
gbt = grohe_bt.GroheBT()
gbt.connect(config['grohe_addr'], user_id, presharedkey)
logger.info("Succesfully connected.")

# Set up webhook
@app.route('/watertime', methods=['POST'])
def respond():
    if (('Secret' not in request.headers) or
        (request.headers['Secret'] != config['secret']) or
        ('Amount' not in request.headers) or
        ('Taste' not in request.headers)):
        logger.warning('Incorrect headers (%s) from IP %s' %(request.headers, request.remote_addr))
        return Response(status=400)
    
    amount = request.headers['Amount'];
    word_taste = request.headers['Taste'].lower();

    taste = None
    if (word_taste == 'still'):
        taste = 1
    elif (word_taste == 'medium'):
        taste = 2
    elif (word_taste == 'sparkle' or word_taste == 'sparkling'):
        taste = 3
    else:
        logger.warning('Impossible taste (%s) requested from IP %s' %(request.headers, request.remote_addr))
        return Response(status=401)

    amount = int(amount)
    if amount < 50 or amount > 2000:
        logger.warning('Impossible amount (%s) requested from IP %s' %(request.headers, request.remote_addr))
        return Response(status=301)

    gbt.dispense_water(amount, taste)
    return Response(status=200)


# set up a heartbeat to keep BT connection alive
@scheduler.task('interval', id='do_heartbeat', seconds=120, misfire_grace_time=900)
def heartbeat():
     logger.info("Running BT heartbeat...")
     logger.info("Got %s." %(gbt.heartbeat()))

# turn on scheduler
class Config:
    SCHEDULER_API_ENABLED = True

# create app
app.config.from_object(Config())

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=config['port'],
            ssl_context=(config['ca_cert'], config['ca_key']),
            use_reloader=False)

    
