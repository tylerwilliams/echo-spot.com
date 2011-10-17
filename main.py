import sys, os
reload(sys)
sys.setdefaultencoding('utf-8')
cwd = os.path.dirname(os.path.abspath( __file__ ))
sys.path.append(cwd)
import json
import uuid
import urllib
import logging
import threading
import ConfigParser
from logging import handlers
import pprint

import web
import spotimeta
from pyechonest import config as pyechonest_config, artist as pyechonest_artist, song as pyechonest_song, playlist as pyechonest_playlist, util as pyechonest_util

os.environ['PYTHON_EGG_CACHE'] = '/tmp'
import memo

config_file = ConfigParser.SafeConfigParser()
config_file.read(os.path.join(cwd, "echospot.conf"))

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

pyechonest_config.ECHO_NEST_API_KEY=config_file.get("echospot", "echo_nest_api_key")
pyechonest_config.TRACE_API_CALLS=True

DUMMY_SPOT_URLS = False
MAX_PLAYLIST_LENGTH = 10
DEFAULT_IMG_URL = "/static/images/default_album.png"
RICKROLL_SONG = {
    'href':"spotify:track:5CXfVcqBAtCAHhnGmoxBZ9", 
    'name':'Nyan Cat!', 
    'artist':'Nyan Cat', 
    'image':DEFAULT_IMG_URL,
}
cacher = memo.Cacher()

urls = ('/create_playlist', 'CreatePlaylist',
        '/get_playlist', 'GetPlaylist',
        '/', 'Index',
        )

def get_spotify_info_for_song(song):
    """
        given a single `pyechonest_song.Song`, search the spotify metadata api
        for it and return a dictionary containing the songs likely `urn` and `artist_urn`
    """
    search_string = "artist:%s title:%s" % (song.artist_name, song.title)
    r = spotimeta.search_track(search_string, page=0)
    if r and 'result' in r and len(r['result']) > 0 and 'href' in r['result'][0]:
        rval = {'urn': r['result'][0]['href'], 'artist_urn':r['result'][0]['artist']['href'] }
    else:
        rval = None
    logger.debug("%s=>%s", search_string, rval)
    return rval


def expand_song_results_for_spotify(songs):
    """
        expand a list of `pyechonest_song.Song` objects
        by adding spotify `urn` and `artist_urn` attributes
    """
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

def create_rickroll_playlist():
    response = {
        "playlist_urn": "spotify:track:5CXfVcqBAtCAHhnGmoxBZ9",
        "playlist": [RICKROLL_SONG]*MAX_PLAYLIST_LENGTH,
        "playlist_id": 'e5eb777c132e42a98e33aa2b68e0f457',
    }
    return response

def clean_and_parse_input(raw_input):
    entities = filter(lambda x: x, raw_input.split(","))
    stripped_entities = [entity.strip() for entity in entities]
    return stripped_entities
    
def classify_input(strings):
    artist_names = []
    song_names = []
    for input in strings:
        if " - " in input:
            song_names.append(input)
        else:
            artist_names.append(input)
    return artist_names, song_names

def resolve_songs(song_names):
    song_ids = []
    
    def resolve_name(song_name, resolved_id_list):
        results = pyechonest_song.search(combined=song_name)
        if results:
            resolved_id_list.append(results[0].id)
    
    for st in range(0, len(song_names), 10):
        threads = []    
        for song_name in song_names[st:st+10]:
            t = threading.Thread(target=resolve_name, args=(song_name, song_ids))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    
    return song_ids

def resolve_artists(artist_names):
    artist_ids = []

    def resolve_name(artist_name, resolved_id_list):
        results = pyechonest_artist.search(artist_name)
        if results:
            resolved_id_list.append(results[0].id)

    for st in range(0, len(artist_names), 10):
        threads = []    
        for artist_name in artist_names[st:st+10]:
            t = threading.Thread(target=resolve_name, args=(artist_name, artist_ids))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

    return artist_ids
        
def create_playlist(raw_input):
    if not raw_input:
        return create_rickroll_playlist()
    
    # sanitize our input
    entities = clean_and_parse_input(raw_input)
    
    artist_names, song_names = classify_input(entities)
    if song_names:
        song_ids = resolve_songs(song_names)
    else:
        song_ids = []
    
    if not (artist_names or song_names):
        return create_rickroll_playlist()
    
    # figure out playlist type based on input
    playlist_type = "song-radio" if len(song_names) > 0 else "artist-radio"
    
    # generate the Echo Nest playlist
    try:
        en_playlist = pyechonest_playlist.static(type=playlist_type, artist=artist_names, song_id=song_ids, buckets=['id:7digital','tracks'], limit=True, results=20)
    except pyechonest_util.EchoNestAPIError:
        artist_ids = resolve_artists(artist_names)
        if artist_ids:
            en_playlist = pyechonest_playlist.static(type=playlist_type, artist_id=artist_ids, song_id=song_ids, buckets=['id:7digital','tracks'], limit=True, results=20)
        else:
            return create_rickroll_playlist()
            
    
    # tack on spotify IDs (and filter out songs we can't find in spotify)
    spotified_playlist = expand_song_results_for_spotify(en_playlist)
    
    # trim to MAX_PLAYLIST_LENGTH
    spotified_playlist = spotified_playlist[:MAX_PLAYLIST_LENGTH]
    
    # assemble the response and cache it
    playlist_id = uuid.uuid4().hex
    playlist_urn = get_spotify_playlist_urn(playlist_id, artist_names, spotified_playlist)
    song_dicts = []
    for song in spotified_playlist:
        sd = {
            'href': song.urn,
            'image': convert_link_to_smaller_image(song.cache['tracks'][0]['release_image']),
            'name': song.title,
            'artist': song.artist_name,
            'artist_href': song.artist_urn
        }
        song_dicts.append(sd)
    
    response = {
        "query": raw_input,
        "playlist_urn": playlist_urn,
        "playlist": song_dicts,
        "playlist_id": playlist_id,
    }
    
    cacher.set_values({playlist_id:response})
    return response


def get_playlist(playlist_id):
    if not playlist_id:
        return create_rickroll_playlist()
    cached_playlist_map = cacher.get_values([playlist_id])
    if not playlist_id in cached_playlist_map or not cached_playlist_map[playlist_id]:
        return create_rickroll_playlist()
    
    return cached_playlist_map[playlist_id]


def get_spotify_playlist_urn(playlist_id, seed_artists, playlist):
    global DUMMY_SPOT_URLS
    if DUMMY_SPOT_URLS:
        return "spotify:track:5CXfVcqBAtCAHhnGmoxBZ9"
    # make a unique playlist name
    allowed_playlist_length = 255-len(playlist_id)-6
    playlist_name = ", ".join(seed_artists)
    if len(playlist_name) > allowed_playlist_length:
        playlist_name = playlist_name[:allowed_playlist_length]+"..."
    # call out to spotserver and make a playlist
    urns = [s.urn for s in playlist]
    playlist_response = json.loads(urllib.urlopen("http://localhost:1337/playlist", json.dumps({'title':playlist_name})).read())
    link = playlist_response['uri']
    t = threading.Thread(target=urllib.urlopen, args=("http://localhost:1337/playlist/%s/add?index=0" % link, json.dumps( urns )))
    t.start()
    return link


class Index:
    def GET(self):
        raise web.seeother("/static/")


class CreatePlaylist:
    def GET(self, *args):
        input = web.input()
        try:
            query = input['query']
            response = create_playlist(query)
        except Exception:
            logging.exception("Couldn't make playlist!")
            response = create_rickroll_playlist()
        # logger.debug(pprint.pformat(response))
        json_playlist = json.dumps(response)
        return json_playlist
    


class GetPlaylist:
    def GET(self, *args):
        input = web.input()
        try:
            playlist_id = input['query']
            response = get_playlist(playlist_id)
        except Exception:
            logging.exception("Couldn't make playlist!")
            response = create_rickroll_playlist()
        # logger.debug(pprint.pformat(response))
        json_playlist = json.dumps(response)
        return json_playlist
    


application = web.application(urls, globals()).wsgifunc()



