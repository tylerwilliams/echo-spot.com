import sys, os
reload(sys)
sys.setdefaultencoding('utf-8')
sys.path.append(os.path.dirname(os.path.abspath( __file__ )))
import time
import json
import uuid
import urllib
import logging
import threading
import ConfigParser
from logging import handlers
from pprint import pprint

import web
import spotimeta
from pyechonest import playlist, config

os.environ['PYTHON_EGG_CACHE'] = '/tmp'
import memo

config_file = ConfigParser.SafeConfigParser()
config_file.read('echospot.conf')

try:
    logging_handler = handlers.WatchedFileHandler(config_file.get("echospot", "log_location"))
except IOError:
    logging_handler = logging.StreamHandler()
    
logging_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging_handler.setFormatter(formatter)

logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(logging_handler)

logger = logging.getLogger(__name__)

config.ECHO_NEST_API_KEY=config_file.get("echospot", "echo_nest_api_key")

### GLOBALS ###
DUMMY_SPOT_URLS = False
MAX_PLAYLIST_LENGTH = 10
DEFAULT_IMG_URL = "/static/images/default_album.png"
RICKROLL_SONG = {
    'href':"spotify:track:5p34sF7EskpzTuW3RGy9fs", 
    'name':'Total Eclipse of the Heart', 
    'artist':'Bonnie Tyler', 
    'image':DEFAULT_IMG_URL
}
cacher = memo.Cacher()
### END GLOBALS ###    
                    
urls = ('/create_playlist', 'CreatePlaylist',
        '/', 'Index',
        )

def get_spotify_info_for_song(song):
    search_string = "artist:%s title:%s" % (song.artist_name, song.title)
    r = spotimeta.search_track(search_string, page=0)
    if r and 'result' in r and len(r['result']) > 0 and 'href' in r['result'][0]:
        rval = {'urn': r['result'][0]['href'], 'artist_urn':r['result'][0]['artist']['href'] }
    else:
        rval = None
    logger.debug("%s=>%s", search_string, rval)
    return rval

def expand_song_results_for_spotify(songs):
    id_to_song_map = dict((song.id,song) for song in songs)
    
    # check our cache
    cache_keys = [song.id for song in songs]
    songid_spotinfo_map = cacher.get_values(cache_keys)
    unresolved_song_ids = list(set(cache_keys)-set(songid_spotinfo_map.keys()))
    logger.debug("%d song_urns cached, %d uncached" % (len(songid_spotinfo_map.keys()), len(unresolved_song_ids)))
    
    # query for missing (and update cache)
    new_songid_spotinfo_data = {}
    
    def resolve_id(song_id, resolved_id_map):
        song = id_to_song_map[song_id]
        spotinfo = get_spotify_info_for_song(song)
        resolved_id_map[song_id] = spotinfo
    
    for st in range(0, len(unresolved_song_ids), 10):
        threads = []    
        for song_id in unresolved_song_ids[st:st+10]:
            t = threading.Thread(target=resolve_id, args=(song_id, new_songid_spotinfo_data))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    
    # pprint(new_songid_spotinfo_data)
    if new_songid_spotinfo_data:
        cacher.set_values(new_songid_spotinfo_data)
    
    # merge our old cached data with new q data
    songid_spotinfo_map.update(new_songid_spotinfo_data)
    
    for song in songs:
        spotinfo = songid_spotinfo_map[song.id]
        if not spotinfo:
            continue
        for key,val in spotinfo.items():
            setattr(song, key, val)
    
    songs_with_audio = filter(lambda song: hasattr(song, 'urn'), songs)
    return songs_with_audio

def convert_link_to_smaller_image(img_link):
    if img_link.endswith("_200.jpg"):
        img_link = img_link.split("_200.jpg")[0]+"_100.jpg"
    return img_link

def create_playlist(artist_name_input):
    if not artist_name_input:
        return [RICKROLL_SONG]*MAX_PLAYLIST_LENGTH
    
    artist_names = filter(lambda x: x, artist_name_input.split(","))
    en_playlist = playlist.static(type='artist-radio', artist=artist_names, buckets=['id:7digital','tracks'], limit=True)
    
    spotified_playlist = expand_song_results_for_spotify(en_playlist)
    songs_with_audio = filter(lambda song: hasattr(song, 'urn'), spotified_playlist)
    songs_with_audio = songs_with_audio[:MAX_PLAYLIST_LENGTH]
    playlist_urn = get_spotify_playlist_urn(artist_names, songs_with_audio)
    json_dicts = []
    for song in songs_with_audio:
        jd = {}
        jd['href'] = song.urn                  # link
        jd['image'] = convert_link_to_smaller_image(song.cache['tracks'][0]['release_image'])
        jd['name'] = song.title                 # track name
        jd['artist'] = song.artist_name     # artist
        jd['artist_href'] = song.artist_urn # artist urn
        json_dicts.append(jd)
    cacher.set_values({playlist_urn:json_dicts})
    return playlist_urn, json_dicts

def get_playlist(playlist_id):
    playlist_dict, json_dicts = cacher.get_values([playlist_id])
    return playlist_dict, json_dicts
    
def get_spotify_playlist_urn(seed_artists, playlist):
    global DUMMY_SPOT_URLS
    if DUMMY_SPOT_URLS:
        return "spotify:user:echo-spot.com:playlist:1Y761QrHO9dIeXFqRuVgSz"
    # make a unique playlist name
    playlist_name = ", ".join(seed_artists)+'-'+uuid.uuid4().hex
    urns = [s.urn for s in playlist]
    jblob = json.dumps({'playlist_name':playlist_name, 'urns':urns})
    params = urllib.urlencode({'request':jblob})
    r = urllib.urlopen("http://localhost:1337/make_playlist", params)
    response = json.loads(r.read())
    link = response['playlist_urn']
    return link

### MAIN URL HANDLERS ###
class Index:
    def GET(self):
        raise web.seeother("/static/")

class CreatePlaylist:
    def GET(self, *args):
        input = web.input()
        try:
            query = input['query']
            response = {}
            playlist_urn, playlist = create_playlist(query)
        except Exception:
            logging.exception("Couldn't make playlist!")
            playlist = dict(enumerate([RICKROLL_SONG]*MAX_PLAYLIST_LENGTH))
            playlist_urn = "spotify:user:echo-spot.com:playlist:1Y761QrHO9dIeXFqRuVgSz"

        response['playlist_urn'] = playlist_urn
        response['playlist'] = playlist
        json_playlist = json.dumps(response)
        logger.debug(json_playlist)
        return json_playlist
 
### END URL HANDLERS ###      

application = web.application(urls, globals()).wsgifunc()



