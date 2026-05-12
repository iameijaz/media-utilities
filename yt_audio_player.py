import subprocess
from yt_dlp import YoutubeDL
import os

def download_audio(youtube_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': 'downloaded_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
    return 'downloaded_audio.mp3'

def play_audio(file_path):
    # Cross-platform simple player; adjust if needed
    if os.name == 'nt':  # Windows
        os.startfile(file_path)
    else:
        subprocess.run(['ffplay', '-nodisp', '-autoexit', file_path])

def main():
    url = input("Enter YouTube URL: ").strip()
    print("Downloading and converting to MP3...")
    mp3_file = download_audio(url)
    print(f"Playing {mp3_file} ...")
    play_audio(mp3_file)

if __name__ == "__main__":
    main()
