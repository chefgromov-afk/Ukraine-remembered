"""
Один раз запустите у себя на компьютере, чтобы получить YT_REFRESH_TOKEN.

  pip install google-auth-oauthlib
  python get_token.py client_secret.json

Откроется браузер: войдите в Google и выберите канал «Забута Україна»
(не Joe's и не Stack & Fold!). В консоли появится refresh token.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
print("\nYT_REFRESH_TOKEN =", creds.refresh_token)
print("YT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
