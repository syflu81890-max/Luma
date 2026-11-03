# SPDX-License-Identifier: GPL-2.0-only
"""Collector-local JSON protocol helpers. No library, database or AI imports."""
import json,re

EXT={'.jpg','.jpeg','.png','.webp','.gif','.bmp','.mp4','.webm','.mov','.mkv','.m4v'}

def json_text(value):
    return json.dumps(value,ensure_ascii=False,default=str)

def media_info(metadata,url=''):
    m=metadata or {};author=m.get('author') or {};author=author if isinstance(author,dict) else {}
    post=str(m.get('tweet_id') or m.get('post_id') or '')
    if not post:
        match=re.search(r'/status/(\d+)',url);post=match[1] if match else ''
    key=f"{post}:{m.get('num') or 1}" if post else ''
    return post,key,author
