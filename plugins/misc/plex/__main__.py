# Copyright (C) 2022 by Fatih Ka. (xybydy), < https://github.com/xybydy >.
#
# This file is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/UsergeTeam/Userge/blob/master/LICENSE >
#
# All rights reserved.

""" plex api support """

import asyncio
import ntpath
import os
import pickle
import re
from functools import wraps
from urllib.parse import unquote
from time import time
from math import floor

from plexapi import utils
from plexapi.exceptions import BadRequest, NotFound
from plexapi.video import Episode, Movie, Show

from userge import userge, Message, get_collection, config,pool
from userge.utils import get_custom_import_re, humanbytes, time_formatter
from userge.plugins.misc.download import url_download
from userge.utils.exceptions import ProcessCanceled

_CREDS: object = None
_SERVERS: list = []
_ACTIVE_SERVER: object = None
_LATEST_RESULTS: list = []




_LOG = userge.getLogger(__name__)
_SAVED_SETTINGS = get_collection("CONFIGS")


VALID_TYPES: tuple = (Movie, Episode, Show)

YTDL_PYMOD = os.environ.get("YOUTUBE_DL_PATH", "yt_dlp")
ytdl = get_custom_import_re(YTDL_PYMOD)

@userge.on_start
async def _init() -> None:
    global _CREDS  # pylint: disable=global-statement
    _LOG.debug("Setting Plex DBase...")
    result = await _SAVED_SETTINGS.find_one({'_id': 'PLEX'}, {'creds': 1})
    _CREDS = pickle.loads(result['creds']) if result else None  # nosec

async def _set_creds(creds: object) -> str:
    global _CREDS  # pylint: disable=global-statement
    _LOG.info("Setting Creds...")
    _CREDS = creds
    result = await _SAVED_SETTINGS.update_one(
        {'_id': 'PLEX'}, {"$set": {'creds': pickle.dumps(creds)}}, upsert=True)
    if result.upserted_id:
        return "`Creds Added`"
    return "`Creds Updated`"

async def _clear_creds() -> str:
    global _CREDS  # pylint: disable=global-statement
    _CREDS = None
    _LOG.info("Clearing Creds...")
    if await _SAVED_SETTINGS.find_one_and_delete({'_id': 'PLEX'}):
        return "`Creds Cleared`"
    return "`Creds Not Found`"

def creds_dec(func):
    """ decorator for check CREDS """
    @wraps(func)
    async def wrapper(self):
        # pylint: disable=protected-access
        if _CREDS:
            await func(self)
        else:
            await self._message.edit("Please run `.plogin` first", del_in=5)
    return wrapper

def servers_dec(func):
    """ decorator for check CREDS """
    @wraps(func)
    async def wrapper(self):
        # pylint: disable=protected-access
        if _SERVERS > 0:
            await func(self)
        else:
            _get_servers()
            _LOG.info("server decorator works")
            await func(self)
    return wrapper

def _get_servers() -> list:
    global _SERVERS

    _SERVERS = [s for s in _CREDS.resources() if 'server' in s.provides]
    return _SERVERS

@pool.run_in_thread
def downloadUrl(url, filename, prog):
    dl_loc = os.path.join(config.Dynamic.DOWN_PATH, filename)
    
    _opts = {
            'outtmpl': dl_loc,
            'retries':999,
            'logger': _LOG,
            'progress_hooks': [prog],
    }

    try:
        x = ytdl.YoutubeDL(_opts)
        dloader = x.download(url)
    except Exception as y_e:  # pylint: disable=broad-except
        _LOG.exception(y_e)
        return y_e
    else:
        return dloader


@pool.run_in_thread
def _search(query, search_type=None) -> list:
    global _ACTIVE_SERVER
    # for server in _SERVERS:
    #     _ACTIVE_SERVER = server.connect()
    results = _ACTIVE_SERVER.search(query)

    if search_type:
        return [i for i in results if i.__class__ == search_type]

    return [i for i in results if i.__class__ in VALID_TYPES]

def __get_filename(part):
    return ntpath.basename(part.file)

@userge.on_cmd("plogin", about={'header': "Login Plex",
'usage': "{tr}plogin [username password]",'examples': "{tr}plogin uname passwd"})
async def plogin(message: Message):
    """ setup creds """
    msg = message.input_str.split(" ")
    if len(msg) != 2:
        await message.edit("Invalid usage. Please check usage `.help plogin`")
    else:
        trimmed_uname = msg[0].strip()
        trimmed_passwd = msg[1].strip()
        if trimmed_uname == "" and trimmed_passwd == "":
            await message.edit("Username or password seem to be empty. Check them.")
            return
        else:
            class Opts:
                username = trimmed_uname
                password = trimmed_passwd
            try:
                account = utils.getMyPlexAccount(Opts)
            except BadRequest as e:
                await message.edit("Plex login failed. Please check logs.")
                _LOG.exception(e)
            else:
                await asyncio.gather(
                _set_creds(account),
                message.edit("`Saved Plex Creds!`", del_in=3, log=__name__))

# u = User(session=account._session, token=account.authenticationToken)

@userge.on_cmd("pserver", about={'header': "Get Plex Server List",
'usage': "{tr}pserver\n{tr}pserver [no of server]",'examples': "{tr}pserver 1",
"description": "Command to get server list and set default active server"})
async def pservers(message: Message):
    """ plex list servers """
    global _SERVERS
    global _ACTIVE_SERVER

    if _CREDS  == None:
        await message.edit("Please login to plex first.")
        return

    if len(_SERVERS) == 0:
        if len(_get_servers()) == 0:
            await message.edit("There is no plex server available")
            return

    query = message.input_str.strip()
    if query:
        try:
            query = int(query)
        except ValueError as e:
            await message.edit("Invalid input for plex server number. Please enter only the server number.")
        else:
            await message.edit(f"Connecting to {_SERVERS[query].name}")
            _ACTIVE_SERVER = _SERVERS[query].connect()
            await message.edit(f"Connected to {_SERVERS[query].name}")
    else:
        msg = ""
        for i in range(len(_SERVERS)):
            msg+=f"{i}. {_SERVERS[i].name}\n"

        await message.edit(f"The servers are:\n{msg}")

@userge.on_cmd("psearch", about={'header': "Search term in plex servers",
'usage': "{tr}psearch [term]",'examples': "{tr}psearch blade runner",
"description": "Search for the term in active server"})
async def psearch(message: Message):
    global _LATEST_RESULTS

    if not _ACTIVE_SERVER:
        await message.edit("There is no active server. Please choose a server first.")
        return

    _LATEST_RESULTS = await _search(message.input_str)

    msg = ""

    for i in range(len(_LATEST_RESULTS)):
        msg+=f"\n{i}. {_LATEST_RESULTS[i].title} {_LATEST_RESULTS[i].year} ({_LATEST_RESULTS[i].type})"

    await message.edit(msg)

@userge.on_cmd("purl", about={'header': "Download given plex url",
                              'usage': "{tr}purl [url]",
                              'examples': "{tr}psearch [flags] URL",
                              'description': "Downloads for the term in active server"})
@creds_dec
async def purl(message: Message):
    global _ACTIVE_SERVER
    items: object = None

    edited = False
    startTime = c_time = time()
    url = message.input_str
    clientid = re.findall('[a-f0-9]{40}', url)
    key = re.findall('key=(.*?)(&.*)?$', url)
    if not clientid or not key:
        await message.edit(f"Unable to parse URL")
        return

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

    _LOG.info("buraya kadar geldik")
    key = unquote(key[0][0])
    try:
        _LOG.info("item key de alindi")
        items = _ACTIVE_SERVER.fetchItem(key)
    except NotFound:
        await message.edit(f"Unable to find URL in the server")
    else:
        for item in items:
            for part in item.iterParts():
                filename = __get_filename(part)
                url = item.url('%s?download=0' % part.key, )
                content = f"{url}|{filename}"

                # try:
                    # dl_loc, d_in = await url_download(message,content)
                # except ProcessCanceled:
                #     await message.canceled()
                #     return
                # except Exception as e_e:  # pylint: disable=broad-except
                #     await message.err(str(e_e))
                #     return
                _LOG.info("download basladi")
                retcode = await downloadUrl(url,filename,__progress)
                _LOG.info(f"download bitti {retcode}")
                if retcode == 0:
                    await message.edit(f"**{filenmae} DOWNLOAD completed in {round(time() - startTime)} seconds**\n")
                else:
                    await message.edit(str(retcode))    