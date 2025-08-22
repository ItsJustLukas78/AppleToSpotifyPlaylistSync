from os.path import dirname, join
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import applemusicpy as applemusic
from dotenv import load_dotenv
import time
import re

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Constants for Spotify and Apple Music
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
SPOTIFY_USERNAME = os.getenv('SPOTIFY_USERNAME')
SPOTIFY_PLAYLIST_ID = os.getenv('SPOTIFY_PLAYLIST_ID')
APPLE_PLAYLIST_ID = os.getenv('APPLE_PLAYLIST_ID')
APPLE_SECRET_KEY_PATH = os.getenv('APPLE_SECRET_KEY_PATH')
APPLE_KEY_ID = os.getenv('APPLE_KEY_ID')
APPLE_TEAM_ID = os.getenv('APPLE_TEAM_ID')


def get_apple_music_tracks(playlist_id):
    """Fetches ALL track details from an Apple Music playlist by handling pagination."""
    print("-> Connecting to Apple Music...")
    try:
        with open(APPLE_SECRET_KEY_PATH, 'r') as f:
            secret_key = f.read()
        am = applemusic.AppleMusic(secret_key=secret_key, key_id=APPLE_KEY_ID, team_id=APPLE_TEAM_ID)

        all_tracks = []
        offset = 0

        print("-> Fetching all tracks from Apple Music playlist (this may take a moment for large playlists)...")
        # Loop to get all pages of tracks
        while True:
            # Fetch one page of tracks using the offset parameter
            # The limit is max 100 per request
            results = am.playlist_relationship(playlist_id, 'tracks', limit=100, offset=offset)

            page_of_tracks = results['data']

            # Process the tracks on the current page
            for track in page_of_tracks:
                # Some tracks might be unavailable or malformed, skip them
                if 'attributes' in track and 'artistName' in track['attributes'] and 'name' in track['attributes']:
                    artist = track['attributes']['artistName']
                    song_name = track['attributes']['name']
                    all_tracks.append({'artist': artist, 'name': song_name})

            # If we received less than 100 tracks, it must be the last page
            if len(page_of_tracks) < 100:
                print(f"  > Reached the end of the playlist.")
                break

            # Otherwise, increase the offset to get the next page in the next loop
            offset += 100
            print(f"  > Fetched {len(all_tracks)} tracks so far...")

            time.sleep(0.2)  # Small delay to avoid hitting API rate limits

        print(f"-> Found a total of {len(all_tracks)} tracks in the Apple Music playlist.")
        return all_tracks

    except Exception as e:
        print(f"Error connecting to Apple Music or fetching playlist: {e}")
        return None

def find_spotify_tracks(sp, apple_tracks):
    """Searches for Apple Music tracks on Spotify automatically."""
    print("-> Searching for tracks on Spotify...")
    found_tracks = []
    not_found_tracks = []

    for i, track in enumerate(apple_tracks):
        artist = track['artist']
        name = track['name']

        query = f"track:{name} artist:{artist}"
        print(f"  ({i + 1}/{len(apple_tracks)}) Searching for: '{name}' by '{artist}'")

        try:
            # --- First Attempt: Exact match ---
            query = f"track:{name} artist:{artist}"
            result = sp.search(q=query, type='track', limit=1)

            # --- Second Attempt: Clean the title if the first attempt fails ---
            if not result['tracks']['items']:
                print("  > No exact match found. Cleaning title and trying again...")
                # Use regex to remove (feat. ...), (with ...), etc.
                cleaned_name = re.sub(r'\s*\([^)]*\)|\s*\[[^\]]*\]', '', name).strip()

                if cleaned_name != name:  # Only search again if the name was actually changed
                    print(f"  > Cleaned title: '{cleaned_name}'")
                    query = f"track:{cleaned_name} artist:{artist}"
                    result = sp.search(q=query, type='track', limit=1)

            # --- Process the final result ---
            if result['tracks']['items']:
                top_result = result['tracks']['items'][0]
                print(f"  > Found on Spotify: '{top_result['name']}' by '{top_result['artists'][0]['name']}'")
                found_tracks.append({
                    'id': top_result['id'],
                    'artist': top_result['artists'][0]['name'],
                    'name': top_result['name']
                })
            else:
                print("  > Could not find a match after cleaning.")
                not_found_tracks.append(f"{artist} - {name}")

        except Exception as e:
            print(f"    - An error occurred while searching for '{name}': {e}")
            not_found_tracks.append(f"{artist} - {name} (Error during search)")

        time.sleep(0.1)  # A smaller delay is fine for this non-interactive version

    print(f"\n-> Search complete.")
    return found_tracks, not_found_tracks

def update_spotify_playlist(sp, playlist_id, track_ids):
    """Clears and updates a Spotify playlist with new tracks."""
    if not track_ids:
        print("No tracks to add. Exiting.")
        return

    print("-> Sorting tracks by artist name...")
    # Sort the list of dictionaries by the 'artist' key
    sorted_tracks = sorted(track_ids, key=lambda x: x['artist'].lower())
    sorted_track_ids = [track['id'] for track in sorted_tracks]

    print(f"-> Updating Spotify playlist...")
    try:
        # Clear the playlist first
        sp.playlist_replace_items(playlist_id, [])

        # Add tracks in chunks of 100 (Spotify API limit)
        for i in range(0, len(sorted_track_ids), 100):
            chunk = sorted_track_ids[i:i + 100]
            sp.playlist_add_items(playlist_id, chunk)

        print("✅ Success! Your Spotify playlist has been updated and sorted by artist.")
    except Exception as e:
        print(f"Error updating Spotify playlist: {e}")


def main():
    """Main function to run the sync process."""
    # Authenticate with Spotify
    scope = "playlist-modify-public"
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=scope,
            username=SPOTIFY_USERNAME
        ))
        sp.me()
    except Exception as e:
        print(f"Could not authenticate with Spotify. Please check your credentials. Error: {e}")
        return

    # Get tracks from Apple Music
    apple_tracks = get_apple_music_tracks(APPLE_PLAYLIST_ID)
    if not apple_tracks:
        return

    # Find corresponding tracks on Spotify
    spotify_tracks, not_found_tracks = find_spotify_tracks(sp, apple_tracks)

    # --- Confirmation Step ---
    print("\n" + "=" * 50)
    print("                 SYNC REVIEW")
    print("=" * 50)

    if not_found_tracks:
        print("\n❌ The following songs could not be found on Spotify:")
        for item in not_found_tracks:
            print(f"  - {item}")

    if spotify_tracks:
        print("\n✅ The following songs will be synced to your Spotify playlist, sorted by artist:")
        # Sort for display purposes, the final sort happens in the update function
        sorted_display_tracks = sorted(spotify_tracks, key=lambda x: x['artist'].lower())
        for track in sorted_display_tracks:
            print(f"  - {track['artist']} - {track['name']}")

    print("=" * 50)

    if not spotify_tracks:
        print("\nNo tracks to sync. Exiting.")
        return

    # Ask for final confirmation
    proceed = input("\nDo you want to proceed with updating the Spotify playlist? (y/n): ").lower()

    if proceed == 'y':
        # If confirmed, update the Spotify playlist
        update_spotify_playlist(sp, SPOTIFY_PLAYLIST_ID, spotify_tracks)
    else:
        print("\nSync cancelled by user.")


if __name__ == "__main__":
    main()