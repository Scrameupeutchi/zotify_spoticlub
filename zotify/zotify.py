import json
import base64
from pathlib import Path
from time import sleep
from pwinput import pwinput
import requests
from librespot.audio.decoders import VorbisOnlyAudioQuality
from librespot.core import Session, OAuth
from librespot.mercury import MercuryRequests
from librespot.proto.Authentication_pb2 import AuthenticationType

from zotify.const import TYPE, \
    PREMIUM, USER_READ_EMAIL, OFFSET, LIMIT, \
    PLAYLIST_READ_PRIVATE, USER_LIBRARY_READ, USER_FOLLOW_READ
from zotify.config import Config

class Zotify:    
    SESSION: Session = None
    DOWNLOAD_QUALITY = None
    CONFIG: Config = Config()

    def __init__(self, args):
        Zotify.CONFIG.load(args)
        Zotify.login(args)

    @classmethod
    def login(cls, args):
        """ Authenticates using OAuth and saves credentials to a file """

        # Build base session configuration (store_credentials is False by default)
        session_builder = Session.Builder()
        session_builder.conf.store_credentials = False

        # Handle stored credentials from config
        if Config.get_save_credentials():
            creds = Config.get_credentials_location()
            session_builder.conf.stored_credentials_file = str(creds)
            if creds and Path(creds).exists():
                # Try using stored credentials first
                try:
                    cls.SESSION = Session.Builder().stored_file(creds).create()
                    return
                except RuntimeError:
                    pass
            else:
                # Allow storing new credentials
                session_builder.conf.store_credentials = True

        # Support login via command line username + token, if provided
        if getattr(args, "username", None) not in {None, ""} and getattr(args, "token", None) not in {None, ""}:
            try:
                auth_obj = {
                    "username": args.username,
                    "credentials": args.token,
                    "type": AuthenticationType.keys()[1]
                }
                auth_as_bytes = base64.b64encode(json.dumps(auth_obj, ensure_ascii=True).encode("ascii"))
                cls.SESSION = session_builder.stored(auth_as_bytes).create()
                return
            except Exception:
                # Fall back to interactive OAuth login if this fails
                pass

        # Fallback: interactive OAuth login with local redirect
        from zotify.termoutput import Printer, PrintChannel

        def oauth_print(url):
            Printer.new_print(PrintChannel.MANDATORY, f"Click on the following link to login:\n{url}")

        port = 4381
        # Config.get_oauth_address() falls back to 127.0.0.1 if unset in this fork
        redirect_address = getattr(Config, "get_oauth_address", None)
        if callable(redirect_address):
            addr = redirect_address()
        else:
            addr = "127.0.0.1"
        redirect_url = f"http://{addr}:{port}/login"

        session_builder.login_credentials = OAuth(MercuryRequests.keymaster_client_id, redirect_url, oauth_print).flow()
        cls.SESSION = session_builder.create()
        return

    @classmethod
    def get_content_stream(cls, content_id, quality):
        return cls.SESSION.content_feeder().load(content_id, VorbisOnlyAudioQuality(quality), False, None)

    @classmethod
    def __get_auth_token(cls):
        return cls.SESSION.tokens().get_token(
            USER_READ_EMAIL, PLAYLIST_READ_PRIVATE, USER_LIBRARY_READ, USER_FOLLOW_READ
        ).access_token

    @classmethod
    def get_auth_header(cls):
        return {
            'Authorization': f'Bearer {cls.__get_auth_token()}',
            'Accept-Language': f'{cls.CONFIG.get_language()}',
            'Accept': 'application/json',
            'app-platform': 'WebPlayer',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv=136.0) Gecko/20100101 Firefox/136.0',
        }

    @classmethod
    def get_auth_header_and_params(cls, limit, offset):
        return {
            'Authorization': f'Bearer {cls.__get_auth_token()}',
            'Accept-Language': f'{cls.CONFIG.get_language()}',
            'Accept': 'application/json',
            'app-platform': 'WebPlayer',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv=136.0) Gecko/20100101 Firefox/136.0',
        }, {LIMIT: limit, OFFSET: offset}

    @classmethod
    def invoke_url_with_params(cls, url, limit, offset, **kwargs):
        headers, params = cls.get_auth_header_and_params(limit=limit, offset=offset)
        params.update(kwargs)
        return requests.get(url, headers=headers, params=params).json()

    @classmethod
    def invoke_url(cls, url, tryCount=0):
        # we need to import that here, otherwise we will get circular imports!
        from zotify.termoutput import Printer, PrintChannel
        headers = cls.get_auth_header()
        response = requests.get(url, headers=headers)
        responsetext = response.text
        try:
            responsejson = response.json()
        except json.decoder.JSONDecodeError:
            responsejson = {"error": {"status": "unknown", "message": "received an empty response"}}

        if not responsejson or 'error' in responsejson:
            if tryCount < (cls.CONFIG.get_retry_attempts() - 1):
                Printer.print(PrintChannel.WARNINGS, f"Spotify API Error (try {tryCount + 1}) ({responsejson['error']['status']}): {responsejson['error']['message']}")
                time.sleep(5)
                return cls.invoke_url(url, tryCount + 1)

            Printer.print(PrintChannel.API_ERRORS, f"Spotify API Error ({responsejson['error']['status']}): {responsejson['error']['message']}")

        return responsetext, responsejson

    @classmethod
    def check_premium(cls) -> bool:
        """ As we always use SpotiClub API, we just return true """
        # return (cls.SESSION.get_user_attribute(TYPE) == PREMIUM)
        return True
