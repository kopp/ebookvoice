#!/usr/bin/python

'''Extract plain text from perspective daily articles.'''



import urllib.request
import re
from html.parser import HTMLParser

import argparse

import requests # TODO: use requests instead of urllib
import configparser # read login info from file
import os.path # exists, expanduser

# setup logger
import logging
import sys
LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler(sys.stdout))


# encoding to assume for web pages
ENCODING = 'utf-8'

# regular expressions to find article content
# Note: one of them should match...
ARTICLE_RE = [
        re.compile(
            r'<div class="content" ng-show="tab==\'article\'">(.*)<div class="infos" ng-show="tab==\'article\'">',
        flags=re.DOTALL),

        re.compile(
            r'<div class="content" ng-show="tab==\'article\'">(.*)<div ng-show="tab==\'discussions\'" class="discussion">',
        flags=re.DOTALL),
        ]

# get article number from url
ARTICLE_NUMBER_FROM_URL_RE = re.compile(r'.*perspective-daily.de/article/([0-9]+).*')

# default output name
DEFAULT_OUT_NAME = 'pd{number}.txt'


# Base url of the page
BASE_URL = 'https://perspective-daily.de'

# Relative path to login
LOGIN_PATH = '/enrol/login'

# RE to get latest article
LATEST_ARTICLE_RE = re.compile(r'<a href="/article/([0-9]+)')

# Section under which username/password need to be stored in config file
CONFIG_FILE_SECTION = 'perspective-daily.de login'
# Key for email address
CONFIG_FILE_EMAIL = 'email'
# Key for password
CONFIG_FILE_PASSWORD = 'password'


# identifiers (commands to get certain articles)
COMMANDS = [ 'latest' ]

# TODO: Add commands
# - latest: get only the latest article
# - unknown: get all unknown ones (store known/unknown in the config file)
# - X-Y
# -> Define map<regexp, function> to interpret the commands?


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
            TagMatcher('div', [('class', 'script')]),
            ]

    # tags that will never get closed -- they need to be ignored in the
    # ignore-stack
    _NEVER_CLOSED_TAGS = [
            'br'
            ]

    # prefix to distinguish closing tags in the stack from opening tags.
    # see in handle_endtag for more details
    _ANTI_TAG_PREFIX = '__anti_tag__'
    _ANTI_TAG_RE = re.compile(_ANTI_TAG_PREFIX + '([a-zA-Z]+)')

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
            if tag in PerspectiveDailyArticleParser._NEVER_CLOSED_TAGS:
                LOG.debug('This is an ignored section (stack is {}) but {} '\
                        'will not be closed, so do not add it to the stack'.format(
                            self._ignore_stack, tag))
            else:
                # check, if an anti-tag is on the stack
                match = PerspectiveDailyArticleParser._ANTI_TAG_RE.match(self._ignore_stack[-1])
                if match:
                    LOG.debug(' -- top most item on stack is anti-tag for {}'.format(
                        match.group(1)))
                    if tag == match.group(1):
                        self._ignore_stack.pop()
                        LOG.debug(' -- this is the tag matching an anti tag; '\
                                'popping (stack is now {})'.format(self._ignore_stack))
                        return
                    else:
                        LOG.debug(' -- tag does not match anti tag')
                        # maybe this will require more elaborate error handling
                # actual stack functionality: push opening to stack
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
            # Maybe it will become necessary to check here for an anti-tag on
            # the stack and compare the current tag to the element before the
            # anti-tag.
            else:
                LOG.warn('Misformat: Closing tag {} found in stack {}'.format(tag, self._ignore_stack))
                # In PD articles, it may happen that a span begins and contains
                # "text</p><p>text".  In order to recover this, add an
                # anti-p-tag from </p> and pop that using the pro-p-tag.
                anti_tag = PerspectiveDailyArticleParser._ANTI_TAG_PREFIX + tag
                LOG.debug('Adding anti-tag {} to stack'.format(anti_tag))
                self._ignore_stack.append(anti_tag)
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



def extract_article_from_html(html):
    '''
    Extract article content from opening to closing div from html text.
    :param html str: correctly encoded html from page or None if unable to extract
    '''
    # try each regexp...
    for regexp in ARTICLE_RE:
        match = regexp.search(html)
        if match:
            article = match.group(1)
            return article
    # if none works, return None
    return None


def get_article_by_url(article_url):
    '''
    Download content of the given web page.
    :return str: article in html (from opening to closing div)
    '''
    req = urllib.request.Request(article_url)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode(ENCODING)
        # search for the article text
        article = extract_article_from_html(html)
        if article:
            return article
        else:
            raise ValueError('Unable to find the article on page {}'.format(article_url))


def get_article_by_number(article_number, session):
    '''
    Download content of the given article number.
    :param article_number int: Number to download
    :param session requests.Session: session that is correctly logged on
    :return str: article in plain text or None if unable to get that article
    '''
    url = '{}/article/{}'.format(BASE_URL, article_number)
    article = session.get(url)
    if not article:
        LOG.warn('Unable to download article number {}'.format(article_number))
        return None
    else:
        LOG.debug('Successfully accessed article no {} at {}: {}'.format(article_number, url, article))
        #LOG.debug('Article text: {}'.format(article.text))
        return extract_article_from_html(article.text)



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


# How to log into a web site:
# http://stackoverflow.com/questions/2910221/how-can-i-login-to-a-website-with-python
# Sending just email and password will fail because a CSRF-Cookie is used.
# When logging in, the login site provides an hidden input field such as
#     <input type='hidden' name='csrfmiddlewaretoken' value='rfA4P2NWy4AyXLin5Z9V82yfp3ZtNpSo' />
# which must be parsed using something like
#       TOKEN_RE = re.compile(r'<input type=\'hidden\' name=\'csrfmiddlewaretoken\' value=\'([a-zA-Z0-9]+)\' />')
#       TOKEN_RE.search(login_page.text).group(1)
# or extracted from a cookie that was set;
# http://stackoverflow.com/questions/13567507/passing-csrftoken-with-python-requests

def log_in(email_address, password):
    '''
    Log into the web site.
    Return session that can be used to access articles.
    :return Tuple<requests.Session, int>: (session that will be logged into the
        site or None in case of an error, number of most recent article or None
        in case of an error).
    '''
    # create the session that will store cookies etc
    session = requests.session()
    # get first token
    login_url = BASE_URL + LOGIN_PATH
    login_page = session.get(login_url)
    if login_page:
        LOG.debug('Logging in to page {}: {}'.format(login_url, login_page))
    else:
        LOG.error('Unable to access login url {}: {}'.format(login_url, login_page))
        return (None, None)
    # setup post request
    try:
        values = {
                'email' : email_address,
                'password' : password,
                'csrfmiddlewaretoken' : session.cookies['csrftoken'],
                }
    except KeyError:
        LOG.error('Unable to extract csrftoken from cookies')
        return (None, None)
    LOG.debug('csrfmiddlewaretoken is {}'.format(values['csrfmiddlewaretoken']))
    # execute post request
    article_overview = session.post(login_url, data=values)
    if article_overview:
        LOG.debug('Posting login to {}; getting {}'.format(login_url, article_overview))
    else:
        LOG.error('Unable to login to {}: {}'.format(login_url, article_overview))
        return (None, None)
    latest_article_match = LATEST_ARTICLE_RE.search(article_overview.text)
    latest_article = None
    if latest_article_match:
        latest_article = int(latest_article_match.group(1))
        LOG.debug('latest article seems to be number {}'.format(latest_article))
    else:
        LOG.error('Unable to get number of the latest article after login')
    return (session, latest_article)


def _get_config_field(config_section, field, ask_user):
    '''
    Extract the filed from the config section.
    If ask_user and the field is not found, ask the user.
    :param config_section Section (ConfigParser()[section]): section to look in
    :param field str: name of the field
    :param ask_user bool: whether to ask the user
    :return str: value or None if unable to get it
    '''
    try:
        value = config_section[field]
    except KeyError:
        LOG.error('{}/{} not found in config file'.format(config_section.name, field))
        if ask_user:
            value = input('field (add this to section {}, key {} in config file): '.format(
                config_section.name, field))
        else:
            value = None
    return value




def read_login_info_from_file(filepath, ask_user):
    '''
    Extract login information from file.
    :param ask_user bool: If true, ask the user for input.
    :return tuple<str, str>: (email, password); each may be None if not in
        config file (or file not found)
    '''
    # TODO: Store password encrypted
    email = None
    password = None
    # try to get input from config file
    if os.path.exists(filepath):
        # read config from file
        config = configparser.ConfigParser()
        config.read(filepath)
        # check that section is there
        try:
            section = config[CONFIG_FILE_SECTION]
            email = _get_config_field(section, CONFIG_FILE_EMAIL, ask_user)
            password = _get_config_field(section, CONFIG_FILE_PASSWORD, ask_user)
        except KeyError:
            LOG.error('Section {} not found in config file {}'.format(CONFIG_FILE_SECTION, filepath))
    else:
        LOG.warning('config file {} not found; make sure to add one'.format(filepath))

    if ask_user:
        if not email:
            email = input('email: ')
        if not password:
            password = input('password: ')
    return (email, password)



if __name__ == '__main__':

    parser = argparse.ArgumentParser(
            description='Download a Perspective Daily article and convert it to plain text',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('identifier', type=str, metavar="url|number|command",
                   help='url or number of the PD article or one command '\
                           'of {}; number or command requires login information'.format(COMMANDS))
    parser.add_argument('--outputfile', type=str,
		       help='Output file for the article, by default outputs to {}.'.format(
                           DEFAULT_OUT_NAME))
    parser.add_argument('--debug', action='store_const', dest='log_level',
            const=logging.DEBUG, default=logging.INFO,
            help='enable debug output')
    parser.add_argument('--config', type=str, metavar='path_to_config_file',
            default='~/.perspective_daily.ini',
            help='alternative path to the configuration file')

    args = parser.parse_args()

    # expand paths
    out_path = args.outputfile # if out path is none, set it later (when article number is known)
    if args.outputfile is not None:
        out_path = os.path.expanduser(args.outputfile)
    config_path = os.path.expanduser(args.config)

    LOG.setLevel(args.log_level)

    # check, whether identifier is url or number
    html = None # extracted content
    if args.identifier.isnumeric():
        number = int(args.identifier)
        # get username/password
        email, password = read_login_info_from_file(config_path, True)
        # login
        session, latest_article = log_in(email, password)
        # access article
        html = get_article_by_number(number, session)
        if not html:
            sys.exit(1)
        # set output path
        out_path = DEFAULT_OUT_NAME.format(number=number)
    elif args.identifier in COMMANDS:
        LOG.error('not yet supported')
        sys.exit(2)
    else: # assume that is is a url
        # try to get url number
        url = args.identifier
        url_match = ARTICLE_NUMBER_FROM_URL_RE.match(url)
        if url_match:
            number = url_match.group(1)
            out_path = DEFAULT_OUT_NAME.format(number=number)
        else:
            out_path = DEFAULT_OUT_NAME.format(number=('_' + re.sub('[^a-zA-Z0-9]', '', url)))
        html = get_article_by_url(url)

    text = parse_article(html)

    LOG.info('Going to write output to file {}'.format(out_path))
    with open(out_path, 'w') as f:
        f.write(text)
