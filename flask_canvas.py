import hmac

from base64 import urlsafe_b64decode as b64decode
from hashlib import sha256
try:
    from simplejson import loads
except ImportError:
    from json import loads
from urllib2 import urlopen

from flask import abort, current_app as app, g, request as frequest

def install(app):
    """ Installs the extension

    :param app: The ``Flask`` app to apply the extension to.
    """
    app.before_request(_before_request)

def request(path, data=None):
    """ Facebook request utility

    Utility function to request resources via the graph API, with the
    format expected by Facebook.
    """
    return loads(urlopen('%s%s?access_token=%s' % (
        'https://graph.facebook.com',
        path,
        g.canvas_user['oauth_token'])).read(), data)

def _has_authorized(app):
    """ Check current user permission set

    Checks the current user permission set against the one being requested
    by the application.
    """
    perms = request('/me/permissions')['data'][0].keys()
    return all(k in perms for k in app.config[
        'CANVAS_SCOPE'].split(','))

def _decode(data):
    """ Decodes the Facebook signed_request parts
    """
    data += "=" * (len(data) % 4)
    return b64decode(data.encode('utf-8'))

def _authorize():
    """ Redirect the user to Facebook's authorization page

    You can't just 302 a user as the app is rendered in an iframe
    """
    return """<!DOCTYPE html>
    <html>
        <head>
            <script>
                var oauth = "https://www.facebook.com/dialog/oauth/?";
                oauth += "client_id=%s";
                oauth += "&redirect_uri=" + encodeURIComponent("%s");
                oauth += "&scope=%s";
                window.top.location = oauth;
            </script>
        </head>
    </html>""" % (app.config['CANVAS_CLIENT_ID'], app.config[
        'CANVAS_REDIRECT_URI'], app.config['CANVAS_SCOPE'],)

def _before_request():
    """ Called before the Flask request is processed

    Capture the request and redirect the user as needed. This function
    will either redirect the user for authorization, or will set
    ``g.canvas_user`` to the dict that Facebook POSTs us in the canvas
    request through the ``signed_request`` param.
    """
    if 'signed_request' not in frequest.form:
        app.logger.error('signed_request not in request.form')
        abort(403)

    encoded_sig, encoded_data = frequest.form['signed_request'].split('.')
    decoded_sig = _decode(encoded_sig)
    decoded_data = loads(_decode(encoded_data))

    if decoded_sig != hmac.new(app.config['CANVAS_CLIENT_SECRET'], 
        encoded_data, sha256).digest():
        app.logger.error('sig doesn\'t match hash')
        abort(403)

    if 'oauth_token' not in decoded_data:
        app.logger.info('unauthorized user, redirecting')
        return _authorize()

    g.canvas_user = decoded_data
    if not app.config.get('CANVAS_SKIP_AUTH_CHECK',
        False) and not _has_authorized(app):
        app.logger.info(
            'user does not have the required permission set. redirecing.')
        return _authorize()
    app.logger.info('all required permissions have been granted')