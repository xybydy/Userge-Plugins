""" work with youtube """

# Copyright (C) 2020-2022 by UsergeTeam@Github, < https://github.com/UsergeTeam >.
#
# This file is part of < https://github.com/UsergeTeam/Userge > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/UsergeTeam/Userge/blob/master/LICENSE >
#
# All rights reserved.

import glob
import os
from math import floor
from pathlib import Path
from time import time

import wget

from userge import userge, Message, config, pool
from userge.utils import time_formatter, humanbytes, get_custom_import_re
from .. import utube
from ..upload import upload

ytdl = get_custom_import_re(utube.YTDL_PYMOD)

LOGGER = userge.getLogger(__name__)

@userge.on_cmd("ytinfo", about={'header': "Get info from ytdl",
                                'description': 'Get information of the link without downloading',
                                'examples': '{tr}ytinfo link',
                                'others': 'To get info about direct links, use `{tr}head link`'})
async def ytinfo(message: Message):
    """ get info from a link """
    await message.edit("Hold on \u23f3 ..")
    _exracted = await utube._yt_getInfo(message.input_or_reply_str)
    if isinstance(_exracted, ytdl.utils.YoutubeDLError):
        await message.err(str(_exracted))
        return
    out = """
**Title** >>
__{title}__

**Uploader** >>
__{uploader}__

{table}
    """.format_map(_exracted)
    if _exracted['thumb']:
        _tmp = await pool.run_in_thread(wget.download)(
            _exracted['thumb'],
            os.path.join(config.Dynamic.DOWN_PATH, f"{time()}.jpg")
        )
        await message.reply_photo(_tmp, caption=out)
        await message.delete()
        os.remove(_tmp)
    else:
        await message.edit(out)


@userge.on_cmd("ytdl", about={
    'header': "Download from youtube",
    'options': {'-a': 'select the audio u-id',
                '-v': 'select the video u-id',
                '-m': 'extract the mp3 in 320kbps',
                '-t': 'upload to telegram',
                '-output': "one of: mkv, mp4, ogg, webm, flv"},
    'examples': ['{tr}ytdl link',
                 '{tr}ytdl -a12 -v120 link',
                 '{tr}ytdl -m -t link will upload the mp3',
                 '{tr}ytdl -m -t -d link will upload '
                 'the mp3 as a document',
                 '{tr}ytdl -output=mp4 -t '
                 'merge output in mp4 and upload to telegram']}, del_pre=True)
async def ytDown(message: Message):
    """ download from a link """
    edited = False
    startTime = c_time = time()

    def __progress(data: dict):
        nonlocal edited, c_time
        diff = time() - c_time
        if (
            data['status'] == "downloading"
            and (not edited or diff >= config.Dynamic.EDIT_SLEEP_TIMEOUT)
        ):
            c_time = time()
            edited = True
            eta = data.get('eta')
            speed = data.get('speed')
            if not (eta and speed):
                return
            out = "**Speed** >> {}/s\n**ETA** >> {}\n".format(
                humanbytes(speed), time_formatter(eta))
            out += f'**File Name** >> `{data["filename"]}`\n\n'
            current = data.get('downloaded_bytes')
            total = data.get("total_bytes")
            if current and total:
                percentage = int(current) * 100 / int(total)
                out += f"Progress >> {int(percentage)}%\n"
                out += "[{}{}]".format(
                    ''.join((config.FINISHED_PROGRESS_STR
                             for _ in range(floor(percentage / 5)))),
                    ''.join((config.UNFINISHED_PROGRESS_STR
                             for _ in range(20 - floor(percentage / 5)))))
            userge.loop.create_task(message.edit(out))

    await message.edit("Hold on \u23f3 ..")
    if bool(message.flags):
        desiredFormat1 = str(message.flags.get('a', ''))
        desiredFormat2 = str(message.flags.get('v', ''))
        m_o_f = message.flags.get('output')
        if m_o_f and m_o_f not in ('mkv', 'mp4', 'ogg', 'webm', 'flv'):
            return await message.err(f"Have you checked {config.CMD_TRIGGER}help ytdl ?")

        if 'm' in message.flags:
            retcode = await utube._mp3Dl([message.filtered_input_str], __progress, startTime)
        elif all(k in message.flags for k in ("a", "v")):
            # 1st format must contain the video
            desiredFormat = '+'.join([desiredFormat2, desiredFormat1])
            retcode = await utube._tubeDl(
                [message.filtered_input_str], __progress, startTime, desiredFormat, m_o_f)
        elif 'a' in message.flags:
            desiredFormat = desiredFormat1
            retcode = await utube._tubeDl(
                [message.filtered_input_str], __progress, startTime, desiredFormat, m_o_f)
        elif 'v' in message.flags:
            desiredFormat = desiredFormat2 + '+bestaudio'
            retcode = await utube._tubeDl(
                [message.filtered_input_str], __progress, startTime, desiredFormat, m_o_f)
        else:
            retcode = await utube._tubeDl(
                [message.filtered_input_str],
                __progress, startTime,
                merge_output_format=m_o_f
            )
    else:
        retcode = await utube._tubeDl([message.filtered_input_str], __progress, startTime)
    if retcode == 0:
        _fpath = ''
        for _path in glob.glob(os.path.join(config.Dynamic.DOWN_PATH, str(startTime), '*')):
            if not _path.lower().endswith((".jpg", ".png", ".webp")):
                _fpath = _path
        if not _fpath:
            await message.err("nothing found !")
            return
        await message.edit(f"**YTDL completed in {round(time() - startTime)} seconds**\n`{_fpath}`")
        if 't' in message.flags:
            await upload(message, Path(_fpath))
    else:
        await message.edit(str(retcode))


@userge.on_cmd("ytdes", about={'header': "Get the video description",
                               'description': 'Get information of the link without downloading',
                               'examples': '{tr}ytdes link'})
async def ytdes(message: Message):
    """ get description from a link """
    await message.edit("Hold on \u23f3 ..")
    description = await utube._yt_description(message.input_or_reply_str)
    if isinstance(description, ytdl.utils.YoutubeDLError):
        await message.err(str(description))
        return
    if description:
        out = '--Description--\n\n\t'
        out += description
    else:
        out = 'No descriptions found :('
    await message.edit_or_send_as_file(out)