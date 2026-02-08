'''
mixxxnp2txt
~~~~~~~~~~~

If --api-url is set, the track data will be sent (POST) to an URL.
The payload will have the following format:
    action = submit_current_track
    artist = current artist
    title = current title
    api_key = --api-key value if set or empty string
'''

import argparse
import datetime
import pathlib
import os
import sqlite3
import sys
import time

import requests


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DEFAULT_CURRENT_FORMAT: str = r'{artist}\n{title}'
DEFAULT_INTERVAL: int = 10


class App:
    Argparser: argparse.ArgumentParser
    args: argparse.Namespace
    mixxx_db_file: pathlib.Path
    out_dir: pathlib.Path = pathlib.Path(__file__).parent.resolve()
    current_out_file: pathlib.Path = out_dir / 'mixxx.current.txt'
    history_out_file: pathlib.Path = out_dir / 'mixxx.history.txt'
    last_track: tuple[str, str] = ('', '')


    def __init__(self) -> None:
        # Setup cli argument parser
        self.Argparser: argparse.ArgumentParser = argparse.ArgumentParser(
            epilog=f"Output directory: {self.out_dir}"
        )
        self.Argparser.add_argument('db_file', type=str, help=f"path to a mixxxdb.sqlite file")
        self.Argparser.add_argument('--current', action='store_true', help="whether to log the current track")
        self.Argparser.add_argument('--history', action='store_true', help="whether to log the track history")
        self.Argparser.add_argument('--interval', metavar='SECONDS', type=int, default=DEFAULT_INTERVAL, help=f"interval in seconds to check for track changes, default={DEFAULT_INTERVAL}")
        self.Argparser.add_argument('--current-format', metavar='FORMAT', type=str, default=DEFAULT_CURRENT_FORMAT, help=f"format for the current track, default='{DEFAULT_CURRENT_FORMAT}'")
        self.Argparser.add_argument('--api-url', metavar='URL', type=str, default=None, help=f"api url to send the current track to, default=None")
        self.Argparser.add_argument('--api-key', metavar='KEY', type=str, default=None, help=f"api key, default=None")

        # Parse given cli arguments
        self.args: argparse.Namespace = self.Argparser.parse_args()

        # Resolve the given database file path to a full one
        self.mixxx_db_file = pathlib.Path(self.args.db_file).resolve()

        # Stop the world from turning if pre-flight checks fail
        if not self.mixxx_db_file.is_file() or not os.access(path=self.mixxx_db_file, mode=os.R_OK, follow_symlinks=True):
            print(f"db_file does not exist or is not readable: {self.mixxx_db_file}")
            sys.exit(1)

        if not self.out_dir.is_dir() or not os.access(path=self.out_dir, mode=os.W_OK, follow_symlinks=True):
            print(f"no write access to output directory: {self.out_dir}")
            sys.exit(2)

        if self.args.interval <= 0:
            print('--interval must be >= 0')
            sys.exit(3)

        if not self.args.current and not self.args.history:
            print("neither --current nor --history are selected, doing nothing.")
            sys.exit(4)


    def main(self) -> None:
        # print('args          ', self.args)
        print('mixxx_db_file ', self.mixxx_db_file)
        print('out_dir       ', self.out_dir)
        print('current       ', self.args.current)
        print('history       ', self.args.history)
        print('interval      ', self.args.interval)
        print()

        is_first_iter: bool = True

        while True:
            try:
                if not is_first_iter:
                    time.sleep(self.args.interval)
                is_first_iter = False

                if self.args.current or self.args.history:
                    track: tuple[str, str] = self.query_current_track()

                    # write data if it has changed since the last check
                    if self.last_track != track:
                        self.last_track = track
                        print(f"{datetime.datetime.now()} | {track[0]} - {track[1]}")
                        self.update_files(track=track)
                        if self.args.api_url:
                            self.send_current_to_api(track=track)

            except KeyboardInterrupt:
                sys.exit(0)

            except Exception as e:
                print(f"BOO: {e}")
                continue


    def query_current_track(self) -> tuple[str, str]:
        con: sqlite3.Connection = sqlite3.connect(database=self.mixxx_db_file)
        cur: sqlite3.Cursor = con.cursor()

        try:
            # Step 1: Get the most recent playlist ID
            cur.execute('SELECT id FROM Playlists ORDER BY id DESC LIMIT 1')
            playlist_result = cur.fetchone()
            if not playlist_result:
                raise Exception("no playlists")

            playlist_id = playlist_result[0]

            # Step 2: Get the most recently added track ID from the playlist
            cur.execute('SELECT track_id FROM PlaylistTracks WHERE playlist_id = :playlist_id ORDER BY pl_datetime_added DESC LIMIT 1', {
                'playlist_id': playlist_id,
            })
            track_result = cur.fetchone()
            if not track_result:
                raise Exception("no tracks in recent playlist")

            track_id = track_result[0]

            # Step 3: Get the track information from the Library table
            cur.execute('SELECT artist, title FROM Library WHERE id = :track_id', {
                'track_id': track_id,
            })
            track = cur.fetchone()

            if not track:
                raise Exception("no track data")

            return (track[0] or '', track[1] or '')

        finally:
            cur.close()
            con.close()


    def update_files(self, track: tuple[str, str]):
        if self.args.current:
            current: str = self.args.current_format
            current = current.replace('{artist}', track[0])
            current = current.replace('{title}', track[1])
            current = current.replace('\\n', '\n')
            with open(file=self.current_out_file, mode='w', encoding='utf-8') as f:
                f.write(current)

        if self.args.history:
            with open(file=self.history_out_file, mode='a', encoding='utf-8') as f:
                f.write(f"{str(datetime.datetime.now(tz=datetime.timezone.utc)).split('.')[0]}  {track[0]} - {track[1]}\n")


    def send_current_to_api(self, track: tuple[str, str]):
        r: requests.Response = requests.post(
            url=self.args.api_url,
            data={
                'action': 'submit_current_track',
                'artist': track[0],
                'title': track[1],
                'api_key': self.args.api_key or '',
            },
            timeout=10,
            headers={
                'user-agent': 'mixxxnp2txt',
            },
        )
        r.raise_for_status()



# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


if __name__ == '__main__':
    Weee = App()
    Weee.main()
