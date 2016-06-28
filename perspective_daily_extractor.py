#!/usr/bin/python

'''Extract plain text from perspective daily articles.'''



import urllib.request
import re
from html.parser import HTMLParser

import argparse

# setup logger
import logging
import sys
LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler(sys.stdout))


# encoding to assume for web pages
ENCODING = 'utf-8'

# regular expression to find article content
ARTICLE_RE = re.compile(
        r'<div class="content" ng-show="tab==\'article\'">(.*)<div class="infos" ng-show="tab==\'article\'">',
        flags=re.DOTALL)





class TagMatcher:
    '''
    Class to match a tag and possibly a set of attributes.
    '''
    def __init__(self, tag, attributes):
        '''
        Define content of the matcher.
        :param tag str: name of the tag
        :param attributes list<tuple<str,str>>: all attributes in format (name, value).
        '''
        self._tag = tag.strip()
        self._attributes = set(attributes)

    def match(self, tag, attrs):
        '''
        Check whether the given tag matches and the given attributes are a
        superset of the attributes given to the constructor for this object
        (i.e. the tag name must match, all attributes given to the constructor
        must be present but if there are more given attributes than that were
        given to the constructor, it matches).
        '''
        if self._tag != tag.strip():
            return False
        else:
            return self._attributes.issubset(set(attrs))


class PerspectiveDailyArticleParser(HTMLParser):
    '''
    Parser that can understand Perspective Daily Articles.

    The parser should output plain text.  It either uses text or ignores it.
    To ignore, it uses a stack where it pushes the ignored tag and pops the end
    tag.  As long as there is stuff on the stack, content is ignored.

    To ignore:
        - stuff within <span class="info">
        - stuff within <cite>
        - stuff within <q class="quote"
        - stuff within <figure>
    '''

    # opening tags from which on to ignore text
    _IGNORE_LIST = [
            TagMatcher('span', [('class', 'info')]),
            TagMatcher('cite', []),
            TagMatcher('q', [('class', 'quote')]),
            TagMatcher('figure', []),
            ]

    # closing tag that produces an endline in the text
    _CLOSING_TAG_ENDLINE_LIST = [ 'p', ]

    def __init__(self):
        HTMLParser.__init__(self)
        self._ignore_stack = []
        self._text = ""

    def handle_starttag(self, tag, attrs):
        '''
        If the start tag begins an ignored section, add it to the _ignore_stack.
        Also push it, if this section is ignored.
        '''
        LOG.debug("Encountered a start tag {} with attributes {}".format(tag, attrs))
        if self._ignore_stack:
            LOG.debug('Since this is in an ignore section (stack is {}), add {} to the stack'.format(
                self._ignore_stack, tag))
            self._ignore_stack.append(tag)
        else:
            if any(ignored.match(tag, attrs) for ignored in PerspectiveDailyArticleParser._IGNORE_LIST):
                LOG.debug(' -- This tag is on the ignored list.  Ignoring stuff from now on.')
                self._ignore_stack.append(tag)
            else:
                LOG.debug(' -- this is not ignored.')

    def handle_endtag(self, tag):
        '''
        If this is in an ignored section, pop the tag or log an error if unable to pop.
        Otherwise introduce a newline for every </p> in the text.
        '''
        LOG.debug("Encountered an end tag {}".format(tag))
        if self._ignore_stack:
            if self._ignore_stack[-1] == tag:
                self._ignore_stack.pop()
            else:
                LOG.warn('Misformat: Closing tag {} found in stack {}'.format(tag, self._ignore_stack))
        else:
            if tag in PerspectiveDailyArticleParser._CLOSING_TAG_ENDLINE_LIST:
                LOG.debug('Introducing a newline in the text')
                self._text += '\n\n'


    def handle_data(self, data):
        LOG.debug("Encountered some data ``{}''".format(data))
        if self._ignore_stack:
            LOG.debug('Ignoring it (stack is {})'.format(self._ignore_stack))
        else:
            # try to find the text
            # ignore whitespace at the beginning/end
            # add one space at the beginning to separate words if the text ended with a non-whitespace
            separator = ''
            text = data.strip()
            if text and self._text and not self._text[-1].isspace() and not text[0].isspace():
                separator = ' '
            self._text += (separator + text)

    def get_text(self):
        '''
        return the text collected up to this point
        '''
        return self._text



def get_article(article_url):
    '''
    Download content of the given web page.
    :return str: article in html (from opening to closing div)
    '''
    req = urllib.request.Request(article_url)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode(ENCODING)
        # search for the article text
        match = ARTICLE_RE.search(html)
        if match:
            article = match.group(1)
            return article
        else:
            raise ValueError('Unable to find the article on page {}'.format(article_url))


def parse_article(article):
    '''
    Parse article content.
    :param article str: article text
    :return str: article in plain text
    '''
    #import xml.etree.ElementTree as ET
    #xml = '<article>' + article + '</article>' # this would be necessary to add add a top level tag as required by xml
    #root = ET.fromstring(xml) # this does not work because the stuff from the website is malformed
    parser = PerspectiveDailyArticleParser()
    parser.feed(article)
    return parser.get_text()





if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Download a Perspective Daily article and convert it to plain text')
    parser.add_argument('url', type=str,
                   help='url of the PD article')
    parser.add_argument('output_file', type=str, default="/tmp/perspective_daily.txt", nargs='?',
		       help='Output file for the article.')
    parser.add_argument('--debug', action='store_const', dest='log_level',
            const=logging.DEBUG, default=logging.INFO,
            help='enable debug output')

    args = parser.parse_args()

    LOG.setLevel(args.log_level)

    html = get_article(args.url)
    text = parse_article(html)
    LOG.info('Going to write output to file {}'.format(args.output_file))
    with open(args.output_file, 'w') as f:
        f.write(text)
