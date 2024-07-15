# this script will ping listenbrainz for a user's now playing song and set it as a discord rich resence

import argparse
import logging
import os
import time
from enum import Enum
from pprint import pformat

import musicbrainzngs
import pylistenbrainz
import requests
from dotenv import load_dotenv
from pypresence import Presence

load_dotenv()
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
LISTENBRAINZ_USER = os.environ.get('LISTENBRAINZ_USER')
MB_APP_NAME = os.environ.get('MB_APP_NAME')
MB_APP_VERSION = os.environ.get('MB_APP_VERSION')
MB_CONTACT = os.environ.get('MB_CONTACT')

# set the logging level based on the --log option;
parser = argparse.ArgumentParser()
parser.add_argument("--log", help="set log level (info [default], debug, error)")
args = parser.parse_args()
if args.log:
    num_log_level = getattr(logging, args.log.upper(), None)
    if not isinstance(num_log_level, int):
        raise ValueError('Invalid log level: %s' % args.log)
    logging.basicConfig(level=num_log_level)
else:
    logging.basicConfig(level=logging.INFO)

now_playing = None

# NOT_PLAYING: user is not not listening
# PLAYING: user is listening; now playing has NOT changed since last status update
# UPDATE: user is listening; now playing has changed since last status update (unused, just send new status)
Status = Enum('Status', ['NOT_PLAYING', 'PLAYING', 'UPDATE'])

client = pylistenbrainz.ListenBrainz()


def get_status():
    global now_playing

    listen = client.get_playing_now(LISTENBRAINZ_USER)
    status = {}

    if listen is None and now_playing is None:
        return Status.NOT_PLAYING

    logging.debug(pformat(vars(listen)))

    np = f"{f'{listen.track_name[:128]}'} | {f'{listen.artist_name} - {listen.release_name}'[:128]}"
    if np == now_playing:
        return Status.PLAYING
    now_playing = np

    # get album art
    album_art = 'icon'

    if listen.release_mbid is not None:
        musicbrainzngs.set_useragent(MB_APP_NAME, MB_APP_VERSION, MB_CONTACT)

        release_info = musicbrainzngs.get_release_by_id(
            listen.release_mbid, includes=['release-groups'])
        logging.debug(pformat(release_info))
        release_group_id = release_info['release']['release-group']['id']

        try:
            result = musicbrainzngs.get_release_group_image_list(release_group_id)
            logging.debug('get_release_group_image_list')
            logging.debug(pformat(result))
        except requests.exceptions.HTTPError as e:
            # handle HTTP errors
            logging.error(f'HTTP error occurred: {e}')
        except musicbrainzngs.ResponseError as e:
            error_code = int(str(e.cause).split()[2][:3])
            if error_code == 400:
                logging.error('Invalid release_group_id')
            elif error_code == 404:
                logging.error('Release group not found')
            elif error_code == 503:
                logging.error('Rate limit exceeded')
            else:
                logging.error('Unknown error')
            # handle MusicBrainz API errors
            logging.error(f'MusicBrainz API error occurred: {e}')
            logging.error(
                f'On release: {listen.artist_name} - {listen.release_name}')
        else:
            # success
            images = result['images']
            image = None
            for img in images:
                if 'Front' in img['types']:
                    image = img
                    break
            if image is not None:
                album_art = img['thumbnails']['large']

    details = listen.track_name[:128]
    state = f'{listen.artist_name} - {listen.release_name}'[:128]

    status = {
        'details': details,
        'state': state,
        'large_image': album_art,
        'large_text': f'{listen.artist_name} - {listen.release_name}'
    }

    if album_art != 'icon':
        status['small_image'] = 'icon'
        status['small_text'] = 'icon'

    logging.debug(status)
    return status

def update_status(RPC):
    status = get_status()
    if status is Status.NOT_PLAYING:
        RPC.clear()
        logging.info('Stopped listening')
    elif status is Status.PLAYING:
        logging.debug(f'Still playing {now_playing}')
    else:
        RPC.update(**status)
        logging.info(f'Now Playing: {now_playing}')

def main():
    RPC = Presence(client_id=DISCORD_CLIENT_ID)
    RPC.connect()

    while True:
        try:
            update_status(RPC)
            time.sleep(15)  # Can only update presence every 15 seconds
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(e)

if __name__ == "__main__":
    main()
