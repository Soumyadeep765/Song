#pls don't forgot to star this repo
#https://github.com/Soumyadeep765/Song/

# deprecated, lyrics not working 
# Spotify have updated things 
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import spotipy
import hashlib
import hmac
import math
import re
from urllib.parse import urlparse
from typing import Optional

#intilizing fastapi server
app = FastAPI(
    title="Spotify Lyrics API",
    description="API to fetch Spotify track details and lyrics",
    version="1.0.0"
)

#Allow cors for localhost request issues 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TOKEN_URL = 'https://open.spotify.com/api/token'
SERVER_TIME_URL = 'https://open.spotify.com/api/server-time'
SPOTIFY_HOME_PAGE_URL = "https://open.spotify.com/"
CLIENT_VERSION = "1.2.46.25.g7f189073"

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US",
    "content-type": "application/json",
    "origin": SPOTIFY_HOME_PAGE_URL,
    "priority": "u=1, i",
    "referer": SPOTIFY_HOME_PAGE_URL,
    "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "spotify-app-version": CLIENT_VERSION,
    "app-platform": "WebPlayer",
}
#Spotify sp_dc cookie extracted from Spotify Web 
DEFAULT_SP_DC = "AQAO1j7bPbFcbVh5TbQmwmTd_XFckJhbOipaA0t2BZpViASzI6Qrk1Ty0WviN1K1mmJv_hV7xGVbMPHm4-HAZbs3OXOHSu38Xq7hZ9wqWwvdZwjiWTQmKWLoKxJP1j3kI7-8eWgVZ8TcPxRnXrjP3uDJ9SnzOla_EpxePC74dHa5D4nBWWfFLdiV9bMQuzUex6izb12gCh0tvTt3Xlg"

#thanks to https://github.com/akashrchandran/syrics/blob/main/syrics/totp.py
#for making that stable one 
class TOTP:
    def __init__(self) -> None:
        self.secret, self.version = self.get_secret_version()
        self.period = 30
        self.digits = 6

    def generate(self, timestamp: int) -> str:
        counter = math.floor(timestamp / 1000 / self.period)
        counter_bytes = counter.to_bytes(8, byteorder="big")

        h = hmac.new(self.secret, counter_bytes, hashlib.sha1)
        hmac_result = h.digest()

        offset = hmac_result[-1] & 0x0F
        binary = (
            (hmac_result[offset] & 0x7F) << 24
            | (hmac_result[offset + 1] & 0xFF) << 16
            | (hmac_result[offset + 2] & 0xFF) << 8
            | (hmac_result[offset + 3] & 0xFF)
        )

        return str(binary % (10**self.digits)).zfill(self.digits)
    
    def get_secret_version(self) -> tuple[str, int]:
        req = requests.get("https://raw.githubusercontent.com/Thereallo1026/spotify-secrets/refs/heads/main/secrets/secrets.json")
        if req.status_code != 200:
            raise ValueError("Failed to fetch TOTP secret and version.")
        data = req.json()[-1]
        ascii_codes = [ord(c) for c in data['secret']]
        transformed = [val ^ ((i % 33) + 9) for i, val in enumerate(ascii_codes)]
        secret_key = "".join(str(num) for num in transformed)
        return bytes(secret_key, 'utf-8'), data['version']
    
class SpotifyLyricsAPI:
    def __init__(self, sp_dc: str = DEFAULT_SP_DC) -> None:
        self.session = requests.Session()
        self.session.cookies.set('sp_dc', sp_dc)
        self.session.headers.update(HEADERS)
        self.totp = TOTP()
        self._login()
        self.sp = spotipy.Spotify(auth=self.token)

    #getting access token 
    def _login(self):
        try:
            server_time_response = self.session.get(SERVER_TIME_URL)
            server_time = 1e3 * server_time_response.json()["serverTime"]
            totp = self.totp.generate(timestamp=server_time)
            params = {
                "reason": "init",
                "productType": "web-player",
                "totp": totp,
                "totpVer": str(self.totp.version),
                "ts": str(server_time),
            }
            req = self.session.get(TOKEN_URL, params=params)
            token = req.json()
            self.token = token['accessToken']
            self.session.headers['authorization'] = f"Bearer {self.token}"
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
#extract track id from url
    def extract_track_id(self, input_str: str) -> str:
        """Extract track ID from URL or return as-is if already an ID"""
        if not input_str:
            raise ValueError("No track ID or URL provided")
        
        # If it's already a valid Spotify ID
        if re.match(r'^[a-zA-Z0-9]{22}$', input_str):
            return input_str
            
        # Try to extract from URL
        parsed = urlparse(input_str)
        if parsed.netloc.endswith('spotify.com'):
            path_parts = parsed.path.split('/')
            if len(path_parts) >= 3 and path_parts[1] == 'track':
                return path_parts[2]
        
        raise ValueError("Invalid Spotify track URL or ID")
#getting track metadata 
    def get_track_details(self, track_id: str) -> dict:
        try:
            track = self.sp.track(track_id)
            return track
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Track not found: {str(e)}")
#getting lyrics as synchronized json format 
    def get_lyrics(self, track_id: str) -> dict:
        try:
            params = 'format=json&market=from_token'
            req = self.session.get(
                f'https://spclient.wg.spotify.com/color-lyrics/v2/track/{track_id}',
                params=params
            )
            if req.status_code != 200:
                return None
            return req.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lyrics fetch failed: {str(e)}")
#format ts in human readable time
    def format_duration(self, ms: int) -> str:
        seconds = int(ms / 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}:{seconds:02d}"
#Formatting track metadata to serve
    def format_track_details(self, track_details: dict) -> dict:
        return {
            'id': track_details['id'],
            'name': track_details['name'],
            'title': track_details['name'],
            'artists': [{
                'name': artist['name'],
                'id': artist['id'],
                'url': artist['external_urls']['spotify']
            } for artist in track_details['artists']],
            'primary_artist': track_details['artists'][0]['name'],
            'album': {
                'name': track_details['album']['name'],
                'id': track_details['album']['id'],
                'url': track_details['album']['external_urls']['spotify'],
                'release_date': track_details['album']['release_date'],
                'total_tracks': track_details['album']['total_tracks'],
                'type': track_details['album']['album_type'],
                'images': track_details['album']['images']
            },
            'release_date': track_details['album']['release_date'],
            'duration': self.format_duration(track_details['duration_ms']),
            'duration_ms': track_details['duration_ms'],
            'image_url': track_details['album']['images'][0]['url'] if track_details['album']['images'] else None,
            'track_url': track_details['external_urls']['spotify'],
            'popularity': track_details['popularity'],
            'preview_url': track_details.get('preview_url'),
            'explicit': track_details.get('explicit', False),
            'type': track_details['type'],
            'uri': track_details['uri']
        }
#joining all lines with \n
    def get_combined_lyrics(self, lines: list, response_type: str = 'plain') -> str:
        if not lines:
            return "No lyrics available"
            
        if response_type == 'plain':
            return '\n'.join([line['words'] for line in lines])
        elif response_type == 'synchronized':
            return '\n'.join([f"[{line['time']}] {line['words']}" for line in lines])
        else:
            return '\n'.join([line['words'] for line in lines])

class LyricsResponse(BaseModel):
    status: str
    details: dict
    lyrics: str
    raw_lyrics: Optional[dict]
    response_type: str

@app.get("/spotify/lyrics", response_model=LyricsResponse, summary="Get track lyrics")
async def get_lyrics(
    id: Optional[str] = Query(None, description="Spotify track ID"),
    url: Optional[str] = Query(None, description="Spotify track URL"),
    format: str = Query('plain', description="Lyrics format (plain or synchronized)"),
    sp_dc: Optional[str] = Query(DEFAULT_SP_DC, description="Spotify sp_dc cookie")
):
    """
    Get lyrics and track details for a Spotify track by either ID or URL.
    
    Parameters:
    - id: Spotify track ID (e.g. 3n3Ppam7vgaVa1iaRUc9Lp)
    - url: Spotify track URL (e.g. https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp)
    - format: Output format for lyrics (plain or synchronized) #TODO
    - sp_dc: Optional Spotify sp_dc cookie for authentication
    """
    if not id and not url:
        raise HTTPException(
            status_code=400,
            detail="Either 'id' or 'url' parameter is required"
        )
    
    try:
        spotify = SpotifyLyricsAPI(sp_dc)
        
        # Extract track ID from either URL or ID
        track_input = id if id else url
        track_id = spotify.extract_track_id(track_input)
        
        # Get track details and lyrics
        track_details = spotify.get_track_details(track_id)
        lyrics = spotify.get_lyrics(track_id)
        
        # Format the response
        formatted_details = spotify.format_track_details(track_details)
        
        combined_lyrics = spotify.get_combined_lyrics(
            lyrics['lyrics']['lines'] if lyrics and 'lyrics' in lyrics else [],
            format
        )

        return {
            "status": "success",
            "details": formatted_details,
            "lyrics": combined_lyrics,
            "raw_lyrics": lyrics,
            "response_type": format
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
