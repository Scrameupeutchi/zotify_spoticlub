from zotify.const import ITEMS, ARTISTS, NAME, ID
from zotify.termoutput import Printer
from zotify.track import download_track
from zotify.utils import fix_filename
from zotify.zotify import Zotify

ALBUM_URL = 'https://api.spotify.com/v1/albums'
ARTIST_URL = 'https://api.spotify.com/v1/artists'


def get_album_tracks(album_id):
    """ Returns album tracklist """
    songs = []
    offset = 0
    limit = 50

    while True:
        resp = Zotify.invoke_url_with_params(f'{ALBUM_URL}/{album_id}/tracks', limit=limit, offset=offset)
        offset += limit
        songs.extend(resp[ITEMS])
        if len(resp[ITEMS]) < limit:
            break

    return songs


def get_album_name(album_id):
    """Return album's primary artist name and album title, honoring configured locale.

    While album/track filenames are now derived from per-track localized metadata,
    we still fetch the album here with locale so any other use remains consistent.
    """
    locale = Zotify.CONFIG.get_locale()
    (raw, resp) = Zotify.invoke_url(f'{ALBUM_URL}/{album_id}?market=from_token&locale={locale}')
    return resp[ARTISTS][0][NAME], fix_filename(resp[NAME])  # type: ignore[index]


def get_artist_albums(artist_id):
    """ Returns artist's albums """
    (raw, resp) = Zotify.invoke_url(f'{ARTIST_URL}/{artist_id}/albums?include_groups=album%2Csingle')
    # Return a list each album's id
    album_ids = [resp[ITEMS][i][ID] for i in range(len(resp[ITEMS]))]  # type: ignore[index]
    # Recursive requests to get all albums including singles an EPs
    while resp['next'] is not None:
        (raw, resp) = Zotify.invoke_url(resp['next'])
    album_ids.extend([resp[ITEMS][i][ID] for i in range(len(resp[ITEMS]))])  # type: ignore[index]

    return album_ids


def download_album(album):
    """ Downloads songs from an album.

    NOTE: We intentionally do NOT pass artist/album names via extra_keys anymore so that the
    placeholders {artist} and {album} remain in the output template until the per-track
    metadata (queried with the configured locale) is applied inside download_track().
    This fixes an issue where album downloads produced filenames with non-localized
    artist names (e.g. 'Eason Chan') while single track downloads correctly used the
    localized variant (e.g. '陳奕迅'). By letting download_track fill these placeholders
    after fetching each track's locale-aware metadata, filenames are now consistent.
    """
    # Still fetch once so we trigger an API call early (may warm caches) but we no longer
    # inject these values into the template; track-level localized metadata will be used.
    get_album_name(album)
    tracks = get_album_tracks(album)
    for n, track in Printer.progress(enumerate(tracks, start=1), unit_scale=True, unit='Song', total=len(tracks)):
        # Only pass dynamic numbering and album_id (useful for custom templates using {album_id}).
        download_track(
            'album',
            track[ID],
            extra_keys={'album_num': str(n).zfill(2), 'album_id': album},
            disable_progressbar=True
        )


def download_artist_albums(artist):
    """ Downloads albums of an artist """
    albums = get_artist_albums(artist)
    for album_id in albums:
        download_album(album_id)
