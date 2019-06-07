import json
from math import floor
from re import match

from django.db.models import Q
from requests import get, post

from playlstr.apikeys import *
from .models import *


def import_spotify(info: dict) -> str:
    """
    Import Spotify playlist and return playlist ID or cause of error if unsuccessful
    :param info: dict where playlist_url is the url of the playlist and access_token is the Spotify access token
    :return: playlist ID or cause of error if unsuccessful
    """
    url = info['playlist_url']
    # Validate URL
    if not (isinstance(url, str) and match(r'^http(s?)://open\.spotify\.com/playlist/.{22}/?', url)):
        return 'Invalid URL'
    playlist_id = url[-23:0] if url[-1] == '/' else url[-22:]
    query_url = 'https://api.spotify.com/v1/playlists/' + playlist_id
    query_headers = {'Authorization': 'Bearer {}'.format(info['access_token'])}
    # Get/create playlist
    playlist_json = get(query_url, headers=query_headers).json()
    playlist = Playlist.objects.get_or_create(spotify_id=playlist_id)[0]
    playlist.name = playlist_json['name']
    playlist.last_sync_spotify = timezone.now()
    playlist.save()
    # Get playlist tracks
    tracks_response = get(query_url + '/tracks', headers=query_headers)
    if tracks_response.status_code != 200:
        return tracks_response.reason
    tracks_json = tracks_response.json()
    try:
        return "Error: " + tracks_json['error_description']
    except KeyError:
        pass
    # Get list of tracks
    index = -1
    while 'next' in tracks_json and tracks_json['next'] is not None:
        for j in tracks_json['items']:
            index += 1
            track = track_from_spotify_json(j['track'])
            PlaylistTrack.objects.create(playlist=playlist, track=track, index=index)
        tracks_json = get(tracks_json['next'], headers=query_headers).json()
    return playlist.playlist_id


def track_from_spotify_json(track_json: dict) -> Track:
    """
    Return a track matching Spotify track JSON
    :param track_json: the Spotify track JSON
    :return: Track matching Spotify JSON
    """
    # Check if track already exists
    query = Q(spotify_id=track_json['id'])
    try:
        query.add(Q(isrc=track_json['external_ids']['isrc']), Q.OR)
    except:
        pass
    track = Track.objects.filter(query).first()
    if track is None:
        title = track_json['name']
        try:
            isrc = track_json['external_ids']['isrc']
        except KeyError:
            isrc = None
        # Create new track
        track = Track.objects.create(title=title)
    else:
        # Ensure existing track has correct spotify id
        track.spotify_id = track_json['id']
    # Get track attributes
    try:
        track.artist = track_json['artists'][0]['name']
    except KeyError:
        pass
    try:
        track.album = track_json['album']['name']
    except KeyError:
        pass
    try:
        track.duration_ms = track_json['duration_ms']
    except KeyError:
        pass
    track.save()
    return track


def valid_spotify_token(token: str) -> bool:
    test_url = 'https://api.spotify.com/v1/tracks/11dFghVXANMlKmJXsNCbNl'
    headers = {'Authorization': 'Bearer {}'.format(token)}
    response = get(test_url, headers=headers)
    return response.status_code == 200


def get_user_spotify_token(user: PlaylstrUser) -> dict:
    if user.spotify_access_token is None or user.spotify_refresh_token is None:
        return {'error': 'unauthorized'}
    if user.spotify_token_expiry is None or user.spotify_token_expiry <= timezone.now():
        updated_token = update_spotify_token_for_user_with_valid_tokens(user)
        if updated_token != 'success':
            return {'error': updated_token}
    return {'access_token': user.spotify_access_token,
            'expires_in': floor((user.spotify_token_expiry - timezone.now()).total_seconds())}


def update_spotify_token_for_user_with_valid_tokens(user: PlaylstrUser) -> str:
    body = {'grant_type': 'refresh_token', 'refresh_token': user.spotify_refresh_token}
    headers = {'Authorization': 'Basic {}'.format(SPOTIFY_B64_CREDS)}
    response = post('https://accounts.spotify.com/api/token', headers=headers, data=body)
    if response.status_code != 200:
        print(response.reason)
        return 'response error'
    try:
        info = response.json()
    except json.JSONDecodeError:
        return 'json error'
    if 'access_token' not in info:
        return 'access token error'
    if 'expires_in' not in info:
        info['expires_in'] = 3600
    if 'refresh_token' in info:
        user.spotify_refresh_token = info['refresh_token']
    user.spotify_access_token = info['access_token']
    try:
        user.spotify_token_expiry = timezone.now() + timezone.timedelta(seconds=int(info['expires_in']))
    except ValueError:
        return 'invalid expiry'
    user.save()
    return 'success'


def spotify_parse_code(info: dict) -> str:
    data = info['post']
    user = info['user']
    headers = {'Authorization': 'Basic {}'.format(SPOTIFY_B64_CREDS)}
    body = {'grant_type': 'authorization_code', 'code': data['code'], 'redirect_uri': data['redirect_uri']}
    response = post('https://accounts.spotify.com/api/token', headers=headers, data=body)
    if response.status_code != 200:
        return response.reason
    try:
        info = response.json()
    except json.JSONDecodeError:
        return 'invalid json'
    if 'access_token' not in info or 'refresh_token' not in info:
        return ''
    if 'expires_in' not in info:
        info['expires_in'] = 3600
    user.spotify_refresh_token = info['refresh_token']
    user.spotify_access_token = info['access_token']
    try:
        user.spotify_token_expiry = timezone.now() + timezone.timedelta(seconds=int(info['expires_in']))
        print(user.spotify_token_expiry)
    except ValueError:
        return ''
    user.save()
