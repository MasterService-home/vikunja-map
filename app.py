"""
Tiny web service that serves the Vikunja map, regenerated from live data.

    GET /         -> the map (HTML)
    GET /map      -> alias
    GET /healthz  -> 'ok'

CACHE_TTL (seconds): 0 = regenerate on every refresh (default, always fresh).
Set VIKUNJA_URL and VIKUNJA_TOKEN in the environment (never in files).
"""
import os
import time

from flask import Flask, Response

import mapgen

app = Flask(__name__)

TTL = float(os.environ.get('CACHE_TTL', '0'))
_cache = {'html': None, 'ts': 0.0}


@app.route('/healthz')
def healthz():
    return 'ok', 200


@app.route('/')
@app.route('/map')
def mapview():
    now = time.time()
    if TTL > 0 and _cache['html'] and (now - _cache['ts']) < TTL:
        return Response(_cache['html'], mimetype='text/html')
    try:
        page = mapgen.generate()
    except KeyError as ex:
        # a required environment variable is missing (e.g. VIKUNJA_URL/TOKEN)
        return Response(
            f"<h1>Missing configuration</h1><p>Environment variable: {ex}</p>",
            status=500, mimetype='text/html')
    except Exception as ex:  # noqa: BLE001 - generic message, never leak the token
        return Response(
            f"<h1>Failed to build the map</h1><pre>{type(ex).__name__}: {ex}</pre>"
            "<p>Check that VIKUNJA_URL is reachable from the container and the token is valid.</p>",
            status=502, mimetype='text/html')
    _cache['html'] = page
    _cache['ts'] = now
    return Response(page, mimetype='text/html')


if __name__ == '__main__':
    # local testing only; the container runs this under gunicorn
    app.run(host='127.0.0.1', port=8000)
