#!/usr/bin/env python
import threading
import logging
import Queue
import time
import os
import spotify
import tempfile
import atexit

from spotify import Link
from spotify.manager import SpotifyContainerManager
logger = logging.getLogger(__name__)

def enum(**enums):
    return type('Enum', (), enums)

CQSTATE = enum(READY=0, CREATING_PL=1, WAITING_FOR_PL=2, ADDING_SONGS=3, WAITING_FOR_SONGS=4, DONE=5)

class JukeboxContainerManager(SpotifyContainerManager):
    def container_loaded(self, c, u):
        # print 'Container loaded !'
        pass

    def playlist_added(self, c, p, i, u):
        # print 'Container: playlist "%s" added.' % p.name()
        pass

    def playlist_moved(self, c, p, oi, ni, u):
        # print 'Container: playlist "%s" moved.' % p.name()
        pass

    def playlist_removed(self, c, p, i, u):
        # print 'Container: playlist "%s" removed.' % p.name()
        pass

class MySSM(threading.Thread):
    api_version = spotify.api_version
    cache_location = tempfile.mkdtemp(dir='/tmp')
    settings_location = cache_location[:]
    appkey_file = os.path.join(os.path.dirname(__file__), 'spotify_appkey.key')
    application_key = open(appkey_file).read()    
    user_agent = 'echo-spot.com'

    def __init__(self, username=None, password=None):
        threading.Thread.__init__(self)
        self.input_queue = Queue.Queue(maxsize=1)
        self.output_queue = Queue.Queue(maxsize=1)
        self.username = username
        self.password = password
        self.remember_me = False
        self.awoken = threading.Event() # used to block until awoken
        self.timer = None
        self.finished = False
        self.session = None
        self.clear_state()
        self.STATE = CQSTATE.READY
        self.asinine_api = True
        self.ctr = None
        self.ctrmgr = JukeboxContainerManager()
        self.logged_in2 = False
        self.ctrmgr.container_loaded = self.container_loaded
        self.playlist_is_loaded = False
        self.tracks_are_loaded = False
        self.connect()
    
    def clear_state(self):
        self.playlist = None
        self.urns = []
        self.playlist_name = ''
        self.playlist_is_loaded = False
        self.tracks_are_loaded = False

    def container_loaded(self, c, u):
        self.logged_in2 = True
        # print 'LOGGED IN!!!'

    def make_playlist(self, playlist_name, urns):
        while not self.logged_in2:
            time.sleep(.1)
            # print 'not logged in yet, cant do shit'
        self.input_queue.put({'playlist_name':playlist_name, 'urns':urns})
        self.input_queue.join()
        return self.output_queue.get(True)
        
    def get_job(self):
        try:
            # get a playlist name and list of urns
            task_dict = self.input_queue.get()
            self.playlist_name = task_dict['playlist_name']
            self.urns = task_dict['urns']
            self.input_queue.task_done()
            self.change_state(CQSTATE.CREATING_PL)
        except Queue.Empty:
            pass
        except Exception:
            logger.exception("malformed job?")

    def playlist_loaded_cb(self, c, u):
        if c.is_loaded():
            self.playlist_is_loaded = True

    def create_playlist(self):
        self.playlist = self.ctr.add_new_playlist(self.playlist_name)
        self.playlist.add_playlist_state_changed_callback(self.playlist_loaded_cb)
        self.change_state(CQSTATE.WAITING_FOR_PL)

    def check_playlist_status(self):
        if not self.playlist_is_loaded:
            return
        if self.playlist.is_loaded():
            self.change_state(CQSTATE.ADDING_SONGS)

    def check_song_status(self):
        if not self.tracks_are_loaded:
            return
        self.change_state(CQSTATE.DONE)
    
    def tracks_added_cb(self, c, u, v):
        if u:
            self.tracks_are_loaded = True
            
    def add_songs(self):
        self.playlist.add_tracks(0, [Link.as_track(Link.from_string(urn)) for urn in self.urns])
        self.playlist.add_playlist_update_in_progress_callback(self.tracks_added_cb)
        self.change_state(CQSTATE.WAITING_FOR_SONGS)

    def return_playlist(self):
        playlist_urn = Link.from_playlist(self.playlist)
        self.output_queue.put(str(playlist_urn))
        self.clear_state()
        self.change_state(CQSTATE.READY)

    def change_state(self, desired_state):
        logger.debug('changing state from %s ==> %s' % (self.STATE, desired_state))
        self.STATE = desired_state

    def connect(self):
        # print 'connect'
        session = spotify.connect(self)
        self.session = session
        # print 'connected'

    def process_events(self):
        self.session.process_events()
    
    def process_work(self):
        if not self.logged_in2:
            return
        if self.STATE == CQSTATE.READY:
            self.get_job()
        elif self.STATE == CQSTATE.CREATING_PL:
            self.create_playlist()
        elif self.STATE == CQSTATE.WAITING_FOR_PL:
            self.check_playlist_status()
        elif self.STATE == CQSTATE.ADDING_SONGS:
            self.add_songs()
        elif self.STATE == CQSTATE.WAITING_FOR_SONGS:
            self.check_song_status()
        elif self.STATE == CQSTATE.DONE:
            self.return_playlist()
        else:
            logger.critical("UNKNOWN STATE: %s" % self.STATE)
    
    def run(self):
        while not self.finished:
            # print 'run loop'
            self.awoken.clear()
            timeout = self.session.process_events()
            self.process_work()
            self.timer = threading.Timer(timeout/1000.0, self.awoken.set)
            self.timer.start()
            self.awoken.wait()
        # print 'run over'
    
    def terminate(self):
        """
        Terminate the current Spotify session.
        """
        self.finished = True
        self.wake()

    def wake(self, session=None):
        """
        This is called by the Spotify subsystem to wake up the main loop.
        """
        if self.timer is not None:
            self.timer.cancel()
        self.awoken.set()

    def logged_in(self, session, error):
        # print 'logged in!'
        if error:
            logger.error('shit'+str(error))
            self.terminate()
        self.session = session
        try:
            # print 'adding playlist container'
            self.ctr = session.playlist_container()
            self.ctrmgr.watch(self.ctr)
        except Exception:
            logger.exception("problem logging in")
    
    def logged_out(self, session):
        logger.info('logged out!')
    
    def connection_error(self, session, error):
        logger.critical(error)
    
    def metadata_updated(self, session):
        pass
    
    def message_to_user(self, session, message):
        pass
    
    def notify_main_thread(self, session):
        pass
    
    def log_message(self, session, message):
        logger.info(message)

