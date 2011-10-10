#!/usr/bin/env python
import json
import logging
import ConfigParser
from logging import handlers

import spotlib
import tornado
import tornado.ioloop
import tornado.web

config_file = ConfigParser.SafeConfigParser()
config_file.read('spotserver.conf')

try:
    logging_handler = handlers.WatchedFileHandler(config_file.get("spotserver", "log_location"))
except IOError:
    logging_handler = logging.StreamHandler()
    
logging_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging_handler.setFormatter(formatter)

logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(logging_handler)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

pt = spotlib.MySSM(config_file.get("spotserver", "premium_spotify_user"), config_file.get("spotserver", "premium_spotify_pass"))
pt.setDaemon(True)
pt.start()

class PlaylistHandler(tornado.web.RequestHandler):
    def post(self, arg):
        global pt
        blobs = self.get_arguments('request', None)
        try:
            blob = blobs[0]
            blob_data = json.loads(blob)
            playlist_name = blob_data['playlist_name']
            song_urns = blob_data['urns']
            playlist = pt.make_playlist(playlist_name, song_urns)
        except Exception:
            logger.exception("Couldn't make playlist!")
            playlist = None
        
        response = {'playlist_urn':playlist}
        self.write(json.dumps(response))

application = tornado.web.Application([
    (r"/make_playlist(.*)", PlaylistHandler),
])

if __name__ == "__main__":
    application.listen(1337)
    tornado.ioloop.IOLoop.instance().start()
