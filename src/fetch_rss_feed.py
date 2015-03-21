# -*- coding: utf-8 -*-
#
#  fetch_rss_feed.py
#  wide-language-index
#

import json
import datetime as dt
import hashlib
import tempfile
import shutil
import glob

import click
import feedparser
import jsonschema
import sh
from pyquery import PyQuery as pq


RSS_FEEDS = 'data/rss_feeds.json'


@click.command()
@click.option('--max-posts', type=int, default=5,
              help='How many posts to fetch from each feed')
@click.option('--language', default=None,
              help='Only scrape the given language code.')
def main(max_posts=5, language=None):
    """
    Fetch new audio podcasts from rss feeds and add them to the index.
    """
    feeds = load_config()
    schema = load_schema()
    seen_urls = scan_index()
    for feed in feeds:
        if language in (feed['language'], None):
            fetch_posts(feed, max_posts, schema, seen_urls)


def load_schema():
    with open('index/schema.json') as istream:
        return json.load(istream)


def fetch_posts(feed, max_posts, schema, seen_urls):
    print('[{0}] {1}'.format(feed['language'], feed['source_name']))

    for post in iter_feed(feed, max_posts, seen_urls):
        sample = post.copy()
        sample['language'] = feed['language']
        sample['source_name'] = feed['source_name']
        fetch_sample(sample)
        save_record(sample)
        jsonschema.validate(sample, schema)

    print()


def fetch_sample(sample):
    url, = sample['media_urls']
    with tempfile.NamedTemporaryFile(suffix='.mp3') as t:
        sh.wget('-O', t.name, url)
        checksum = md5_checksum(t.name)
        sample['checksum'] = checksum
        filename = 'samples/{language}/{language}-{checksum}.mp3'.format(
            **sample
        )
        shutil.copy(t.name, filename)


def save_record(sample):
    filename = 'index/{language}/{language}-{checksum}.json'.format(**sample)
    s = json.dumps(sample, indent=2, sort_keys=True)
    with open(filename, 'w') as ostream:
        ostream.write(s)


def md5_checksum(filename):
    with open(filename, 'rb') as istream:
        return hashlib.md5(istream.read()).hexdigest()


def scan_index():
    seen_urls = set()
    for f in glob.glob('index/*/*.json'):
        with open(f) as istream:
            r = json.load(istream)
            url = r['source_url']
            seen_urls.add(url)

    return seen_urls


def iter_feed(feed, max_posts, seen_urls):
    rss_url = feed['rss_url']
    feed = feedparser.parse(rss_url)
    for i, e in enumerate(feed.entries[:max_posts]):
        title = e['title']
        source_url = e['link']

        if source_url in seen_urls:
            print('{0}. {1} (skipped)'.format(i + 1, title))
            continue

        print('{0}. {1}'.format(i + 1, title))
        media_url = detect_media_url(e, feed)
        t = e['published_parsed']
        d = dt.date(year=t.tm_year, month=t.tm_mon, day=t.tm_mday)
        yield {
            'title': title,
            'media_urls': [media_url],
            'source_url': source_url,
            'date': str(d),
        }


def detect_media_url(e, feed):
    url = e['link']
    if url.endswith('.mp3'):
        return url

    audio_links = [l['href'] for l in e['links']
                   if l['href'].endswith('.mp3')]
    if len(audio_links) > 1:
        raise Exception('too many audio files to choose from')
    elif len(audio_links) == 1:
        return audio_links[0]

    d = pq(url=url)
    files = set([a.attrib['href'] for a in d('a')
                 if 'href' in a.attrib
                 and a.attrib['href'].endswith('.mp3')])
    if len(files) > 1:
        raise Exception('too many audio files to choose from')

    return list(files)[0]


def load_config():
    with open(RSS_FEEDS) as istream:
        return json.load(istream)


if __name__ == '__main__':
    main()