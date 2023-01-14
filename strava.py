
import json
from stravalib.client import Client

def init_client(client_id, client_secret, refresh_token):
    client = Client()

    refresh_response = client.refresh_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token)
    client.access_token = refresh_response['access_token']
    client.refresh_token = refresh_response['refresh_token']
    client.token_expires_at = refresh_response['expires_at']
    return client

def load_from_config(filepath):
    with open('strava_secrets.json') as f:
        strava_secrets = json.load(f)
        STRAVA_CLIENT_ID = int(strava_secrets['client_id'])
        STRAVA_CLIENT_SECRET = strava_secrets['client_secret']
        STRAVA_REFRESH_TOKEN = strava_secrets['refresh_token']
    return init_client(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN)
