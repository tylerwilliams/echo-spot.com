import re
import time
import logging
import contextlib

import memcache

logger = logging.getLogger(__name__)

@contextlib.contextmanager
def ctimer(message):
    tic = time.time()
    yield
    toc = time.time()
    logger.info("took %.2f ms to %s" % ((toc-tic)*1000,message))

class stopwatch:
    """
        A decorator that will log the time (in mS) taken to execute a 
        function.
    """
    def __call__(self, f):
        def wrapper(*args, **kwargs):
            with ctimer(f.func_name):
                rval = f(*args, **kwargs)
            return rval
        return wrapper


class Cacher(object):
    def __init__(self, hostname='localhost', port=11211):
        self.mc_servers = ["%s:%s" % (hostname, port)]
        self.connected = False
        self.mc = None
        self._reconnect()
    
    def _reconnect(self):
        mc = memcache.Client(self.mc_servers, debug=1)
        if mc.set('memcache','fuckingrules'):
            self.mc = mc
            self.connected=True
        else:
            logger.warning('unable to connect to memcache @ %s', self.mc_servers[0])

    def hash_args(self, args, kwargs):
        # sort them so they always hash the same
        # and remove non-alphanumeric characters
        # we want to make cache keys that are intelligible (if possible)
        # so that we can easily clear one of them if we need to
        args = sorted(map(lambda x: re.sub(r'\W+', '', x), list(args)))
        for key in kwargs:
            if isinstance(kwargs[key], list):
                kwargs[key].sort()
            if kwargs[key] is None or kwargs[key] == '' or kwargs[key] == []:
                kwargs.pop(key)
        kwargs = sorted(kwargs.items())
        arghash = ''
        if args:
            args = "_".join(args)
            arghash += args
        if kwargs:
            kwargs = "_".join(map(lambda x: re.sub(r'\W+', '', "%s%s" % x), kwargs))
            arghash += kwargs
        if arghash:
            arghash = arghash.encode('ascii')
            arghash = arghash[:199]+"_"
        return arghash

    def set_values(self, some_dict, *args, **kwargs):
        """
            save all k/vs from some_dict in memcache
        """
        with ctimer("set_values"):
            prefix = self.hash_args(args, kwargs)
            if self.mc:
                rval = self.mc.set_multi(some_dict, key_prefix=prefix)
            else:
                # all keys were failures
                rval = [prefix+key for key in some_dict.keys()]
        return rval

    def get_values(self, keylist, *args, **kwargs):
        """
            get a dict for k/vs from keylist
        """
        # convert keys to ascii
        keylist = [key.encode('ascii') for key in keylist]
        with ctimer("get_values"):
            prefix = self.hash_args(args, kwargs)
            if self.mc:
                rval = self.mc.get_multi(keylist, key_prefix=prefix)
            else:
                rval = {}
        return rval

    def delete_values(self, keylist, *args, **kwargs):
        """
            del keys/vals from memcache based on keylist
        """
        with ctimer("delete_values"):
            prefix = self.hash_args(args, kwargs)
            if self.mc:
                rval = self.mc.delete_multi(keylist, key_prefix=prefix)
            else:
                rval = False
        return rval
