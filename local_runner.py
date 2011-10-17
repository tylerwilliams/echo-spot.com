import logging
import web

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("starting server...")
    import main
    main.DUMMY_SPOT_URLS = True
    main.pyechonest_config.TRACE_API_CALLS = True
    web.debug = True
    from main import *
    app = web.application(main.urls, globals())
    app.run()
