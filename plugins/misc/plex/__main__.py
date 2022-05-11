# Copyright (C) 2022 by Fatih Ka. (xybydy), < https://github.com/xybydy >.
#
# This file is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/UsergeTeam/Userge/blob/master/LICENSE >
#
# All rights reserved.

""" plex api support """

from ast import Not
import asyncio
import ntpath
import os
import pickle
import re
from functools import wraps
from urllib.parse import unquote
from xml.dom import NotFoundErr

from plexapi import utils
from plexapi.exceptions import BadRequest, NotFound
from plexapi.video import Episode, Movie, Show

from userge import userge, Message, get_collection
from userge.plugins.misc.download import url_download

_CREDS: object = None
_SERVERS: list = []
_ACTIVE_SERVER: object = None
_LATEST_RESULTS: list = []


_LOG = userge.getLogger(__name__)
_SAVED_SETTINGS = get_collection("CONFIGS")


VALID_TYPES: tuple = (Movie, Episode, Show)


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

@servers_dec
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

    _LATEST_RESULTS = _search(message.input_str)

    msg = ""

    for i in range(len(_LATEST_RESULTS)):
        msg+=f"\n{i}. {_LATEST_RESULTS[i].title} {_LATEST_RESULTS[i].year} ({_LATEST_RESULTS[i].type})"

    await message.edit(msg)

@userge.on_cmd("purl", about={'header': "Download given plex url",
                              'usage': "{tr}purl [url]",
                              'examples': "{tr}psearch [flags] URL",
                              'flags': {'-g': "gdrive upload"},
                              'description': "Downloads for the term in active server"})
@creds_dec
async def purl(message: Message):
    global _ACTIVE_SERVER
    items: object = None

    url = message.input_str
    clientid = re.findall('[a-f0-9]{40}', url)
    key = re.findall('key=(.*?)(&.*)?$', url)
    if not clientid or not key:
        await message.edit(f"Unable to parse URL")
        return

    # cid = clientid[0]
    key = unquote(key[0][0])
    try:
        items = _ACTIVE_SERVER.fetchItem(key)
    except NotFound:
        await message.edit(f"Unable to find URL in the server")
    else:
        for item in items:
            for part in item.iterParts():
                filename = __get_filename(part)
                url = item.url('%s?download=0' % part.key, )
                content = f"{url}|{filename}"

                dl_loc, bune = await url_download(message,content)


    # for r in _SERVERS:
        # if r.clientIdentifier == cid:
            # _ACTIVE_SERVER = r.connect()
            # link = _ACTIVE_SERVER.fetchItem(key)
            # await message.edit(f"Got the link - {link}")
            # return
@userge.on_cmd("put", about={'header': "Download given plex url",
                              'usage': "{tr}purl [url]",
                              'examples': "{tr}psearch [flags] URL",
                              'flags': {'-g': "gdrive upload"},
                              'description': "Downloads for the term in active server"})
async def pit(message: Message):
    await message.client.send_message(message.chat.id,".ls")


def get_item_from_url(url, account=None):
    global server
    # Parse the ClientID and Key from the URL
    clientid = re.findall('[a-f0-9]{40}', url)
    key = re.findall('key=(.*?)(&.*)?$', url)
    if not clientid or not key:
        raise SystemExit('Cannot parse URL: %s' % url)
    clientid = clientid[0]
    key = unquote(key[0][0])
    # Connect to the server and fetch the item
    servers = [r for r in account.resources() if r.clientIdentifier == clientid]
    if len(servers) != 1:
        raise SystemExit('Unknown or ambiguous client id: %s' % clientid)
    server = servers[0].connect()
    return server.fetchItem(key)

def download_url(url, account):
    items = get_item_from_url(url, account)

    for item in items:
        if isinstance(item, Show):
            for episode in item.episodes():
                if not os.path.exists(episode.parentTitle):
                    os.mkdir(episode.parentTitle)
                for part in episode.iterParts():
                    filename = __get_filename(part)
                    url = item.url('%s?download=0' % part.key, )
        else:
            for part in item.iterParts():
                filename = __get_filename(part)
                url = item.url('%s?download=0' % part.key, )