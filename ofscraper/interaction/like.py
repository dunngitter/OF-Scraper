r"""
                                                             
        _____                                               
  _____/ ____\______ ________________    ____   ___________ 
 /  _ \   __\/  ___// ___\_  __ \__  \  /  _ \_/ __ \_  __ \
(  <_> )  |  \___ \\  \___|  | \// __ \(  <_> )  ___/|  | \/
 \____/|__| /____  >\___  >__|  (____  /\____/ \___  >__|   
                 \/     \/           \/            \/         
"""

import random
import time
import logging
from typing import Union
import asyncio
import httpx

from tenacity import retry,stop_after_attempt,wait_random

from rich.progress import Progress
from rich.progress import (
    Progress,
    MofNCompleteColumn,
    BarColumn,
    TextColumn,
    SpinnerColumn
)
from rich.style import Style
from ..api import timeline
from ..constants import favoriteEP, postURL
from ..utils import auth
import ofscraper.api.archive as archive
import ofscraper.api.pinned as pinned
import ofscraper.utils.console as console
import ofscraper.constants as constants
from ofscraper.utils.semaphoreDelayed import semaphoreDelayed
import ofscraper.prompts.prompts as prompts

sem = semaphoreDelayed(1)
log=logging.getLogger(__package__)
import ofscraper.utils.args as args_



def get_posts(headers, model_id):
    pinned_posts=[]
    timeline_posts=[]
    archived_posts=[]
    args=args_.getargs()

    args.posts = list(map(lambda x:x.capitalize(),(args.posts or prompts.like_areas_prompt())
    ))
    if ('Pinned' in args.posts or 'All' in args.posts):
        pinned_posts = asyncio.run(pinned.get_pinned_post(headers, model_id))
    if ('Timeline' in args.posts or 'All' in args.posts):
        timeline_posts = asyncio.run(timeline.get_timeline_post(headers, model_id))
    if ('Archived' in args.posts or 'All' in args.posts):
        archived_posts = asyncio.run(archive.get_archived_post(headers, model_id))
    log.debug(f"[bold]Number of Post Found[/bold] {len(pinned_posts) + len(timeline_posts) + len(archived_posts)}")
    return pinned_posts + timeline_posts + archived_posts


def filter_for_unfavorited(posts: list) -> list:
    output=list(filter(lambda x:x.get("isFavorite")==False,posts))
    log.debug(f"[bold]Number of unliked post[/bold] {len(output)}")
    return output




def filter_for_favorited(posts: list) -> list:
    output=list(filter(lambda x:x.get("isFavorite")==True,posts))
    log.debug(f"[bold]Number of liked post[/bold] {len(output)}")
    return output



def get_post_ids(posts: list) -> list:
    valid_post=list(filter(lambda x:x.get("isOpened")==True,posts))
    return list(map(lambda x:x.get("id"),valid_post))
   


def like(headers, model_id, username, ids: list):
    asyncio.run(_like(headers, model_id, username, ids, True))


def unlike(headers, model_id, username, ids: list):
    _like(headers, model_id, username, ids, False)



async def _like(headers, model_id, username, ids: list, like_action: bool):
    title = "Liking" if like_action else "Unliking"
    global sem
    sem.delay=3
    with Progress(SpinnerColumn(style=Style(color="blue")),TextColumn("{task.description}"),BarColumn(),MofNCompleteColumn(),console=console.shared_console) as overall_progress:
        tasks=[]
        task1=overall_progress.add_task(f"{title} posts...\n",total=len(ids))

        [tasks.append(asyncio.create_task(_like_request(headers,id,model_id,username)))
            for id in ids]
        for count,coro in enumerate(asyncio.as_completed(tasks)):
                id=await coro
                log.debug(f"ID: {id} Performed {'like' if like_action==True else 'unlike'} action")
                if count+1%60==0:
                    sem.delay=3
                elif count+1%50==0:
                    sem.delay=30   
                overall_progress.update(task1,advance=1,refresh=True)

        
        

@retry(stop=stop_after_attempt(constants.NUM_TRIES),wait=wait_random(min=constants.OF_MIN, max=constants.OF_MAX),reraise=True)   
async def _like_request(headers,id,model_id,username):
    async with sem:
        with httpx.Client(http2=True, headers=headers) as c:
            url = favoriteEP.format(id, model_id)
            auth.add_cookies(c)
            c.headers.update(auth.create_sign(url, headers))
            r = c.post(url)
    
            if not r.is_error or r.status_code == 400:
                return id
                     
            else:
                _handle_err(r, postURL.format(i, username))

    


def _handle_err(param: Union[httpx.Response, httpx.TransportError], url: str) -> str:
    message = 'unable to execute action'
    status = ''
    try:
        if isinstance(param, httpx.Response):
            json = param.json()
            if 'error' in json and 'message' in json['error']:
                message = json['error']['message']
            status = f'STATUS CODE {param.status_code}: '
        else:
            message = str(param)
    except:
        pass
    log.info(f'{status}{message}, post at {url}')
    raise Exception()
