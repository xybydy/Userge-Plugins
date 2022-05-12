""" work with youtube """

# Copyright (C) 2020-2022 by UsergeTeam@Github, < https://github.com/UsergeTeam >.
#
# This file is part of < https://github.com/UsergeTeam/Userge > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/UsergeTeam/Userge/blob/master/LICENSE >
#
# All rights reserved.

from userge import userge, config, pool
from userge.utils import get_custom_import_re
from ..upload import upload

ytdl = get_custom_import_re(utube.YTDL_PYMOD)

LOGGER = userge.getLogger(__name__)

@pool.run_in_thread
def _yt_description(link):
    try:
        x = ytdl.YoutubeDL({'no-playlist': True, 'logger': LOGGER}).extract_info(
            link, download=False)
    except Exception as y_e:  # pylint: disable=broad-except
        LOGGER.exception(y_e)
        return y_e
    else:
        return x.get('description', '')


@pool.run_in_thread
def _yt_getInfo(link):
    try:
        x = ytdl.YoutubeDL(
            {'no-playlist': True, 'logger': LOGGER}).extract_info(link, download=False)
        thumb = x.get('thumbnail', '')
        formats = x.get('formats', [x])
        out = "No formats found :("
        if formats:
            out = "--U-ID   |   Reso.  |   Extension--\n"
        for i in formats:
            out += (f"`{i.get('format_id', '')} | {i.get('format_note', None)}"
                    f" | {i.get('ext', None)}`\n")
    except Exception as y_e:  # pylint: disable=broad-except
        LOGGER.exception(y_e)
        return y_e
    else:
        return {'thumb': thumb, 'table': out, 'uploader': x.get('uploader_id', None),
                'title': x.get('title', None)}


@pool.run_in_thread
def _tubeDl(url: list, prog, starttime, uid=None, merge_output_format=None):
    _opts = {'outtmpl': os.path.join(config.Dynamic.DOWN_PATH, str(starttime),
                                     '%(title)s-%(format)s.%(ext)s'),
             'logger': LOGGER,
             'writethumbnail': True,
             'prefer_ffmpeg': True,
             'postprocessors': [
                 {'key': 'FFmpegMetadata'}]}
    if merge_output_format and merge_output_format in ('mkv', 'mp4', 'ogg', 'webm', 'flv'):
        _opts.update({'merge_output_format': merge_output_format})
    _quality = {'format': 'bestvideo+bestaudio/best' if not uid else str(uid)}
    _opts.update(_quality)
    try:
        x = ytdl.YoutubeDL(_opts)
        x.add_progress_hook(prog)
        dloader = x.download(url)
    except Exception as y_e:  # pylint: disable=broad-except
        LOGGER.exception(y_e)
        return y_e
    else:
        return dloader


@pool.run_in_thread
def _mp3Dl(url, prog, starttime):
    _opts = {'outtmpl': os.path.join(config.Dynamic.DOWN_PATH, str(starttime), '%(title)s.%(ext)s'),
             'logger': LOGGER,
             'writethumbnail': True,
             'prefer_ffmpeg': True,
             'format': 'bestaudio/best',
             'postprocessors': [
                 {
                     'key': 'FFmpegExtractAudio',
                     'preferredcodec': 'mp3',
                     'preferredquality': '320',
                 },
                 # {'key': 'EmbedThumbnail'},  ERROR: Conversion failed!
                 {'key': 'FFmpegMetadata'}]}
    try:
        x = ytdl.YoutubeDL(_opts)
        x.add_progress_hook(prog)
        dloader = x.download(url)
    except Exception as y_e:  # pylint: disable=broad-except
        LOGGER.exception(y_e)
        return y_e
    else:
        return dloader
