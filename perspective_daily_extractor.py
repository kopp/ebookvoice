#!/usr/bin/python3

'''Extract plain text from perspective daily articles.'''

# pylint: disable=wrong-import-order
# pylint: disable=bad-continuation
# pylint: disable=line-too-long
# pylint: disable=invalid-name
# pylint: disable=logging-format-interpolation


import urllib.request
import re
from html.parser import HTMLParser

import argparse

import requests # TODO: use requests instead of urllib
import configparser # read login info from file
import os.path # exists, expanduser
import subprocess # call external tool pdftotext

from enum import Enum

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

        re.compile(
            r'<div class="content article" ng-show="tab==\'article\'">(.*)(<p class="formobile">.*)?<div class="gift share" ng-show="tab==\'article\'">',
        flags=re.DOTALL),
        ]

AUDIO_RE = re.compile(r"<audio-player url='(.*)' title=.*></audio-player>")

## pdf
# footnote: some spaces, then # or *, the a number, then a newline and again some spaces.
FOOTNOTE_RE = re.compile(' +(#|\*)[0-9]+\n *')
# fint the end of a pdf that contains additional information
ADD_INFO_RE = re.compile('\nZusätzliche Informationen\n.*', re.DOTALL)
# unnecessary newlines -- those that are between two lines of text
# Note: The '(?= )' is a _lookahead_; it makes sure, that the symbol following
#       the matching group (the break) is \S -- but it is not part of the
#       match, that will be used for substitution.  '(?<= )' is a lookbehind,
#       which likewise asserts, that the preceeding symbol is \S...
UNNECESSARY_NEWLINES_RE = re.compile('(?<=\S)( *\n *)(?=\S)')
# unnecessary whitespace
UNNECESSARY_WHITESPACE_RE = re.compile('(?<=\n)( +)')
# fix for PD conversion errors:
# Text contains things such as
#     Ein paar Augenblicke, die sidenote##<##über 220.000
#     Menschen##>####<##quelle##>####<##http://www.un.org/apps/news/story.asp
#     unüberprüfbare Hochrechnungen liegen weit über den offiziellen
#     Schätzungen der UN bei 316.000 Todesopfern (englisch, 2013)##>## das
#     Leben kosteten
# here, the part between 'sidenote##<##' and '##>##' is necessary, the rest to
# be ignored.
SIDNOTE_ERRORS_RE = re.compile(r'sidenote##<##(.*)##>####<##(.*)##>####<##(.*)##>##')

# get article number from url
ARTICLE_NUMBER_FROM_URL_RE = re.compile(r'.*perspective-daily.de/article/([0-9]+).*')

# default output name
DEFAULT_OUT_NAME = 'pd{number}.{ext}'
# patterns for output file should look like this
OUT_PATTERN_RE = re.compile('.*{number}.*')


# Base url of the page
BASE_URL = 'https://perspective-daily.de'

# Relative path to login
LOGIN_PATH = '/enrol/login'

# RE to get latest article
LATEST_ARTICLE_RE = re.compile(r'<a href="/article/([0-9]+)')

# Section under which username/password need to be stored in config file
CONFIG_FILE_SECTION_LOGIN =         'perspective-daily.de login'
# Key for email address
CONFIG_FILE_KEY_EMAIL =             'email'
# Key for password
CONFIG_FILE_KEY_PASSWORD =          'password'
# section for known articles
CONFIG_FILE_SECTION_ARTICLES =      'perspective-daily.de articles'
# Key for known articles
CONFIG_FILE_KEY_KNOWN =             'known articles'
# Key for non-existent articles (numbers that are not used)
CONFIG_FILE_KEY_NONEXISTENT =       'unasigned numbers'


# commands to get certain articles
# this is a map of identifier to description
COMMANDS = {
        'latest' :          'Return only the latest article.',
        'unknown':          'Return all unknown articles',
        '<numA>-<numB>' :   'Return a range of articles identified by numbers from numA to numB'
        }

COMMAND_RANGE_RE = re.compile('^([0-9]+)-([0-9]+)$')


class ArticleFormat(Enum):
    '''enum specifying the type of article used'''
    HTML = 1
    PDF = 2
    AUDIO = 3
    AUDIO_OVER_HTML = 5 # use audio if available, fallback to HTML; use for requests
    AUDIO_OVER_PDF = 6  # ", fallback to PDF "

def is_audio_preferred(article_format):
    '''Check, whether the given ArticleFormat is one that prefers Audio over something.'''
    return (ArticleFormat.AUDIO_OVER_HTML == article_format) or (ArticleFormat.AUDIO_OVER_PDF == article_format)

def extension_for_format(article_format):
    '''Return the default extension for the given article format.'''
    if article_format in [ArticleFormat.HTML, ArticleFormat.PDF]:
        return 'txt'
    elif article_format is ArticleFormat.AUDIO:
        return 'mp3'
    else:
        raise NotImplementedError('Unable to propose file extension for format {}'.format(article_format))

def get_secondary_format(article_format):
    '''Get the not-preferred format if available.'''
    if article_format is ArticleFormat.AUDIO_OVER_HTML:
        return ArticleFormat.HTML
    if article_format is ArticleFormat.AUDIO_OVER_PDF:
        return ArticleFormat.PDF
    else:
        raise ValueError('Format {} has no not-preferred format'.format(article_format))


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
        - stuff within <span class="script">
    '''

    # opening tags from which on to ignore text (keep in sync with class comment!)
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
            'br',
            'input', # see e.g. pd43
            ]

    # these tags are closed often, but not always :-/
    _SOMETIMES_NOT_CLOSED_TAGS = [
            'img', # most often it's <img .../> but there is also e.g. pd67
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
            elif tag in PerspectiveDailyArticleParser._NEVER_CLOSED_TAGS:
                LOG.warning('Encountered end tag {} which should never happen; ignoring it.'.format(tag))
            # Maybe it will become necessary to check here for an anti-tag on
            # the stack and compare the current tag to the element before the
            # anti-tag.
            else:
                LOG.warn('Misformat: Closing tag {} found in stack {}'.format(tag, self._ignore_stack))

                # check, whether the tag before is not closed always
                if self._ignore_stack[-1] in PerspectiveDailyArticleParser._SOMETIMES_NOT_CLOSED_TAGS:
                    # if so, pop that
                    LOG.warn('This may be because the previous tag was not '\
                            'closed (which is a known PD issue).  Removing '\
                            'that and trying to handle this end tag again.')
                    self._ignore_stack.pop()
                    self.handle_endtag(tag)
                else:
                    # otherwise check other recovery options
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



def read_known_numbers_from_config(filename, sectionname, keyname):
    '''
    Read list of known numbers from given config file.
    :return set<int>: list of known numbers
    '''
    c = configparser.ConfigParser()
    if not c.read(filename):
        raise ValueError('Config file at {} does not exist'.format(filename))
    # check if section exists
    try:
        section = c[sectionname]
    except KeyError:
        raise ValueError('Config file {} should contain a section "{}"'.format(
            filename, sectionname))
    try:
        values_one_string = section[keyname]
    except KeyError:
        # if keyword does not exist, no articles are known
        LOG.info('There is no key "{}" in section "{}" of file {} with known '\
                'numbers; assuming none'.format(keyname, sectionname, filename))
        return set() # empty
    values = set() # collect numbers
    values_strings = re.sub('\s', '', values_one_string).split(',')
    for value in values_strings:
        if value: # ignore empty strings
            if not value.isnumeric():
                LOG.warning('error: value "{}" of key "{}" in section "{}" of '\
                        'file {} should be numeric; ignoring it.'.format(
                            value, keyname, sectionname, filename))
            else:
                values.add(int(value))
    return values


def append_write_known_numbers_to_config(filename, sectionname, keyname, numbers, break_after=10):
    '''
    Modify the given configuration file to contain the new list of numbers,
    overwriting the old.
    :param numbers iterable<convertible-to-int>: numbers to write
    :param break_after int: insert newline after thus many numbers; set to 0 to
    not insert breaks.
    '''
    c = configparser.ConfigParser()
    c.read(filename)
    # make sure that numbers are really numbers and unique
    new_numbers = set()
    for num in numbers:
        try:
            value = int(num)
            new_numbers.add(value)
        except ValueError as e:
            LOG.error('Ignoring non-numeric value {} from numbers list ({})'.format(num, e))
    current_numbers = read_known_numbers_from_config(filename, sectionname, keyname)
    # numbers to write are new numbers and known numbers
    numbers_to_write = current_numbers.union(new_numbers)
    # check, if a change is necessary
    # this is the case, when the new numbers are already contained in the current numbers
    if current_numbers == numbers_to_write:
        LOG.debug('new numbers are already contained in known numbers; '\
                'nothing needs to be changed in config file')
    else:
        LOG.info('numbers changed from {} to {}'.format(current_numbers, numbers_to_write))
        values_one_string = '' # formatted string
        nrs_in_line = 0 # number of numbers in the current line
        for num in sorted(numbers_to_write): # output numbers sorted
            if break_after and nrs_in_line == break_after:
                values_one_string += '\n' # add newline and indent
                nrs_in_line = 0
            values_one_string += ' {},'.format(num)
            nrs_in_line += 1
        # commit new values to config struct
        c[sectionname][keyname] = values_one_string.strip()
        # write to file
        with open(filename, 'w') as cfg:
            c.write(cfg)



def extract_article_from_html(html):
    '''
    Extract article content from opening to closing div from html text.
    :param html str: correctly encoded html from page
    :return str: html content of the article or None if unable to extract
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
    raise NotImplementedError('Check, whether we want to download a pdf, if so, do not use extract_article_from_html.')
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode(ENCODING)
        # search for the article text
        article = extract_article_from_html(html)
        if article:
            return article
        else:
            raise ValueError('Unable to find the article on page {}'.format(article_url))


def get_article_by_number(article_number, session, article_format):
    '''
    Download content of the given article number.
    :param article_number int: Number to download
    :param session requests.Session: session that is correctly logged on
    :param article_format ArticleFormat: select the format to get
    :return (str|bytes|requests.Response, ArticleFormat):
        if it was possible to fetch the article: content in html (from
        opening to closing div) or content of the pdf or audio file in bytes,
        second parameter is the article format fetched.
        If unable to fetch it, GET-reply that evalutes to False and None.
    '''
    LOG.debug('Format {} requested for article no {}'.format(article_format, article_number))
    url = '{}/article/{}'.format(BASE_URL, article_number)
    # in both cases (html, pdf), access the html article
    article = session.get(url)
    if not article:
        LOG.warning('Unable to download article number {} at {}'.format(article_number, url))
        return article, None
    else:
        LOG.debug('Successfully accessed article no {} at {}: {}'.format(article_number, url, article))
        #LOG.debug('Article text: {}'.format(article.text))
        # if audio is preferred, try to get it and return that
        if is_audio_preferred(article_format):
            LOG.debug('Audio is preferred for article {}'.format(article_number))
            audio_url = extract_audio_url_if_available(article.text)
            if audio_url:
                LOG.debug('Article no {} has audio at {}'.format(article_number, audio_url))
                audio_response = session.get(audio_url)
                if not audio_response:
                    LOG.warn('Unable to download audio for article number {} from {}'.format(article_number, audio_url))
                    return audio_response, None
                else:
                    LOG.debug('downloaded audio for article number {} successfully'.format(article_number))
                    return audio_response.content, ArticleFormat.AUDIO
            else:
                article_format = get_secondary_format(article_format)
                LOG.debug('Article no {} has no audio; now looking for format {}'.format(article_number, article_format))
        # if no audio is requested or it's not possible to get some, check for other formats
        if article_format is ArticleFormat.PDF:
            # for the pdf we need the redirected url (which contains some magic
            # code after the article number) ...
            redirect_url = article.url
            # ... where we can append `/pdf`
            pdf_url = redirect_url + '/pdf'
            # and now we can access the data
            pdf_response = session.get(pdf_url)
            if not pdf_response:
                LOG.warn('Unable to download pdf article for number {} at {}'.format(article_number, pdf_url))
                return pdf_response, None
            else:
                LOG.debug('Successfully accessed pdf of article no {} at {}'.format(article_number, pdf_url))
                # article is complete pdf
                return pdf_response.content, ArticleFormat.PDF
        elif article_format is ArticleFormat.HTML:
            # article is only part of the html -- extract that
            return extract_article_from_html(article.text), ArticleFormat.HTML
        else:
            raise NotImplementedError('format {} not implemented in get_article_by_number'.format(article_format))

def extract_audio_url_if_available(article_html):
    '''
    Get the url of an audio file from the html content of the article.
    If not available, return None.
    '''
    match = AUDIO_RE.search(article_html)
    if match:
        return match.group(1)
    else:
        return None



def filter_raw_pdf_text(pdf_text):
    '''
    Filter the raw output of the text extraction.
    This removes things like footnotes and additional information from the end
    of the article.
    '''
    # filter footnote marks from text
    pdf_text = FOOTNOTE_RE.sub(' ', pdf_text)
    # remove additional information at the end of the article.
    pdf_text = ADD_INFO_RE.sub('', pdf_text)
    # remove unnecessary newlines
    pdf_text = UNNECESSARY_NEWLINES_RE.sub(' ', pdf_text)
    # remove leading whitespace
    pdf_text = UNNECESSARY_WHITESPACE_RE.sub('', pdf_text)
    # fix errors in pdf export, when sidenotes are exported
    pdf_text = SIDNOTE_ERRORS_RE.sub(r'\1', pdf_text)
    return pdf_text


def extract_text_from_pdf(pdf_content):
    '''
    Extract the article content from the pdf.
    :param pdf_content bytes: pdf as bytes stream.
    :return string: (long) string with article content.
    '''
    # these parameters are found by experimenting with gv and the
    # appropriate command line
    # Note: The coordinate system starts at the top left corner, x
    #       is to the right, y goes down -- so y is handled
    #       differently in gv.
    x_param = '-x 70 -W 500'
    y_param = { True    : '-y 110 -H 595', # first page
                False   : '-y 80 -H 660', # rest
                }
    pg_param = { True   : '-f 1 -l 1', # first page
                 False  : '-f 2',
                 }
    def _make_args(first_page):
        '''
        Generate process call with arguments as list of strings.
        :param first_page bool: True for first page, False otherwise
        '''
        return 'pdftotext -nopgbrk -layout {pg} {x} {y} - -'.format(
                pg=pg_param[first_page], x=x_param, y=y_param[first_page]
                ).split()

    def _extract(first_page):
        '''Extract text from pdf.
        :raise FileNotFoundError: if tool is not installed
        '''
        extractor = subprocess.Popen(_make_args(first_page),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        out, err = extractor.communicate(input=pdf_content)
        if err:
            LOG.error('error returned by conversion tool: {}'.format(err))
        return out

    out_bytes = _extract(True) + _extract(False)
    out_text = out_bytes.decode('utf-8') # pdftotext returns utf-8 encoded text

    return filter_raw_pdf_text(out_text)



class Article:
    '''
    Simple struct to hold article text
    :param identifier: (hopefully) unique identifier for this article.
    :param content: unparsed content of the article (may be binary audio, binary pdf or html)
    :param article_format ArticleFormat: Format of the article
    '''
    def __init__(self, identifier, content=None, article_format=None):
        self._identifier = identifier
        self._raw_content = content
        self._format = article_format

    def get_identifier(self):
        return self._identifier

    def is_impossible_to_get(self):
        '''Whether it is impossible to get the article.'''
        return self._raw_content is None

    def get_text(self):
        '''
        Return text as plain text (i.e. not parsed).
        '''
        return self._raw_content

    def get_format(self):
        '''
        Return the kind of available format (text/audio).
        '''
        return self._format

    def get_article_number(self):
        '''
        Return the article number if it's known, otherwise return None
        '''
        try:
            numeric_value = int(self._identifier)
            return numeric_value
        except ValueError:
            return None

    def get_article_as_plain_text(self):
        '''
        Parse article content.
        Assumes that self._raw_content is article text in html from opening to closing div
        :return str: article in plain text
        '''
        if self._format is ArticleFormat.HTML:
            #import xml.etree.ElementTree as ET
            #xml = '<article>' + article + '</article>' # this would be necessary to add add a top level tag as required by xml
            #root = ET.fromstring(xml) # this does not work because the stuff from the website is malformed
            parser = PerspectiveDailyArticleParser()
            parser.feed(self._raw_content)
            return parser.get_text()
        elif self._format is ArticleFormat.PDF:
            return extract_text_from_pdf(self._raw_content)
        elif self._format is ArticleFormat.AUDIO:
            raise ValueError('Unable to generate text from an audio type')
        else:
            raise NotImplementedError('It seems like the content is neither in html nor in pdf format; the new format {} not yet implemented.'.format(self._format))


    def get_article_as_bytes(self):
        if self._format in [ArticleFormat.HTML, ArticleFormat.PDF]:
            return self.get_article_as_plain_text().encode('UTF-8')
        else:
            return self._raw_content


def get_many_articles(numbers_or_urls, session, article_format):
    '''
    Try to access a list of articles referenced either by url or by number.
    :param numbers_or_urls iterable<str|convertible-to-int>: elements to download
    :param article_format ArticleFormat: Format in which to download the article.
    :return (list<Article>, list<identifier>): Each article is returned as
        Article object.  Its identifier is set to the article number.  If
        unable to get a number for the article, some other identifier (e.g.
        from url) is used.  If it's not possible to get an article, its
        identifier is returned in the second list.
    '''
    articles = list()
    failures = list()
    for identifier in numbers_or_urls:
        content = None
        unique_identifier = None # may be number or derived from url
        returned_format = None
        if is_number(identifier):
            number = int(identifier)
            content, returned_format = get_article_by_number(number, session, article_format)
        else:
            content = get_article_by_url(identifier)
            # get unique_identifier
            url_match = ARTICLE_NUMBER_FROM_URL_RE.match(identifier)
            if url_match:
                unique_identifier = url_match.group(1)
            else:
                unique_identifier = 'url_' + re.sub('[^a-zA-Z0-9]', '', identifier)
        # sort outcome of operation depending on success/failure
        if not content:
            LOG.warning('Unable to get article {} due to {}'.format(identifier, content))
            failures.append(identifier)
        else:
            articles.append(Article(identifier, content, returned_format))
    # return what was fetched
    return articles, failures


def save_list_of_articles(articles, outfile_pattern):
    '''
    Store the given articles to outfiles generated from given pattern.
    :param articles list<Article>: valid articles to store
    :param outfile_pattern str: pattern for outfile, should include a
        "{number}" and "{ext}" for the extension.
    '''
    for art in articles:
        extension = extension_for_format(art.get_format())
        filename = outfile_pattern.format(number=art.get_identifier(), ext=extension)
        LOG.info('Going to write output to file {}'.format(filename))
        with open(filename, 'wb') as f:
            f.write(art.get_article_as_bytes())



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
    session.headers.update({'Referer': login_url}) # required since 2018-10-15
    article_overview = session.post(login_url, data=values)
    if article_overview:
        LOG.debug('Posting login to {}; getting {}'.format(login_url, article_overview))
    else:
        LOG.error('Unable to login to {}: {} due to {}'.format(login_url, article_overview, article_overview.text))
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
            section = config[CONFIG_FILE_SECTION_LOGIN]
            email = _get_config_field(section, CONFIG_FILE_KEY_EMAIL, ask_user)
            password = _get_config_field(section, CONFIG_FILE_KEY_PASSWORD, ask_user)
        except KeyError:
            LOG.error('Section {} not found in config file {}'.format(CONFIG_FILE_SECTION_LOGIN, filepath))
    else:
        LOG.warning('config file {} not found; make sure to add one'.format(filepath))

    if ask_user:
        if not email:
            email = input('email: ')
        if not password:
            password = input('password: ')
    return (email, password)



def is_number(str_or_int):
    '''
    Return True when input is either an integer or a string convertible to an integer.
    '''
    try:
        value = int(str_or_int)
        return True
    except ValueError:
        return False


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
            description='Download a Perspective Daily article and convert it to plain text',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument('identifiers', type=str, metavar="url|number|command", nargs='+',
            help='url or number of the PD article or one command '\
                    'of {}.  Number or command requires login information.'.format(
                        ', '.join(['"{}" ({})'.format(c, d) for c, d in COMMANDS.items()])))
    parser.add_argument('--outputfile', type=str, metavar='outfile_pattern',
            default=DEFAULT_OUT_NAME,
            help='Output file for the article.  If you intend to '\
                    'output multiple files, make sure to use "{number}" in '\
                    'that name; this will be substituted by the article '\
                    'number (or other identification), where "{ext}" will get '\
                    'replaced by the extension (txt or mp3).')
    parser.add_argument('--debug', action='store_const', dest='log_level',
            const=logging.DEBUG, default=logging.INFO,
            help='enable debug output')
    parser.add_argument('--config', type=str, metavar='path_to_config_file',
            default='~/.perspective_daily.ini',
            help='alternative path to the configuration file')
    parser.add_argument('--use-html', action='store_const', dest='article_format',
            const=ArticleFormat.HTML, default=ArticleFormat.PDF,
            help='Extract the article from html (default is to extract from pdf).')
    parser.add_argument('--prefer-text', action='store_const', dest='use_audio_if_available',
            const=False, default=True,
            help='Even if an audio version is available, get the text '
                    '(default is to get audio if available).')

    args = parser.parse_args()

    LOG.setLevel(args.log_level)

    # expand paths
    out_path = os.path.expanduser(args.outputfile)
    config_path = os.path.expanduser(args.config)

    # check, whether out_path contains a pattern
    if not OUT_PATTERN_RE.match(out_path):
        LOG.warning('The output file pattern should contain a place holder '\
                'for the article number; see --help.  If you download '\
                'multiple files, this is a bad idea.')

    # interpret identifier
    identifiers_to_get = set() # this will be all the elements to download
    session_latest_article = (None, None) # if a login was necessary, store session and latest article

    for identifier in args.identifiers:
        LOG.debug('Going to interpret identifier {}'.format(identifier))
        # check, whehter it's a range of numbers
        range_match = COMMAND_RANGE_RE.match(identifier)
        if range_match:
            numberA = int(range_match.group(1))
            numberB = int(range_match.group(2))
            number_begin =  max(min(numberA, numberB), 1) # smaller number; make sure >= 1
            number_end =    max(max(numberA, numberB), 1) # larger number; make sure >= 1
            LOG.debug('Going to add the range from {} to {} to articles to get.'.format(
                number_begin, number_end))
            identifiers_to_get = identifiers_to_get.union(set(range(number_begin, number_end+1)))
        # command latest
        elif identifier == 'latest':
            if session_latest_article[1] is None: # check, if information is available
                email, password = read_login_info_from_file(config_path, True)
                session_latest_article = log_in(email, password)
            if any(el is None for el in session_latest_article):
                LOG.error('Unable to log in.  Skipping {}.'.format(identifier))
                continue
            identifiers_to_get.add(session_latest_article[1])
        # command unknown
        elif identifier == 'unknown':
            # find out what's the latest article
            if session_latest_article[1] is None: # check, if information is available
                email, password = read_login_info_from_file(config_path, True)
                session_latest_article = log_in(email, password)
            if any(el is None for el in session_latest_article):
                LOG.error('Unable to log in.  Skipping {}.'.format(identifier))
                continue
            # add all from first to latest without invalid or known ones
            to_get = set(range(1, session_latest_article[1]))
            # remove known ones from the list
            try:
                known = read_known_numbers_from_config(config_path,
                        CONFIG_FILE_SECTION_ARTICLES, CONFIG_FILE_KEY_KNOWN)
                to_get = to_get.difference(known)
            except ValueError as e:
                LOG.info('Unable to get all information about known/invalid '\
                        'articles from config file: {}'.format(e))
            # finally add those to the list to get
            identifiers_to_get = identifiers_to_get.union(to_get)
        # default: url
        else:
            # unable to interpret identifier as command; add it as identifier
            # directly
            identifiers_to_get.add(identifier)


    # remove articles from known invalid numbers
    try:
        invalid = read_known_numbers_from_config(config_path,
                CONFIG_FILE_SECTION_ARTICLES, CONFIG_FILE_KEY_NONEXISTENT)
        if invalid.intersection(identifiers_to_get):
            LOG.info('The following article numbers are probably invalid: {}; '\
                    'removing them from the query'.format(invalid))
            identifiers_to_get = identifiers_to_get.difference(invalid)
    except ValueError as e:
        LOG.info('Unable to get all information about known/invalid '\
                'articles from config file: {}'.format(e))

    # if any number is requested...
    if any(is_number(val) for val in identifiers_to_get):
        # ... make sure that a login is/was performed
        if any(el is None for el in session_latest_article):
            email, password = read_login_info_from_file(config_path, True)
            session_latest_article = log_in(email, password)
        # ... and substitute urls through their numbers if possible
        substitutions = list() # tupes (from, to)
        for identifier in identifiers_to_get:
            if not is_number(identifier):
                url_match = ARTICLE_NUMBER_FROM_URL_RE.match(identifier)
                if url_match:
                    number = url_match.group(1)
                    LOG.debug('Substituting recognized url "{}" through number {}'.format(
                        identifier, number))
                    substitutions.append((identifier, number))
        for substitute in substitutions:
            identifiers_to_get.remove(substitute[0])
            identifiers_to_get.add(substitute[1])

    if any(el is None for el in session_latest_article):
        LOG.error('Unable to log in.')

    # this is what should get fetched
    LOG.info('Going to get the following identifiers: {}'.format(identifiers_to_get))

    # check, what format to get
    article_format = args.article_format
    if args.use_audio_if_available:
        if ArticleFormat.HTML == article_format:
            article_format = ArticleFormat.AUDIO_OVER_HTML
        elif ArticleFormat.PDF == article_format:
            article_format = ArticleFormat.AUDIO_OVER_PDF
        else:
            raise NotImplementedError('--prefer-audio not implemented for this format')


    # finally start to get stuff
    articles, failures = get_many_articles(identifiers_to_get, session_latest_article[0], article_format)

    # store articles
    save_list_of_articles(articles, out_path)

    # store known articles
    known_numbers = [art.get_article_number() for art in
            filter(lambda a: a.get_article_number() is not None, articles)
            ]
    LOG.info('Storing the following article numbers as known: {}'.format(known_numbers))
    append_write_known_numbers_to_config(
            config_path, CONFIG_FILE_SECTION_ARTICLES, CONFIG_FILE_KEY_KNOWN,
            known_numbers)

    # store the non-existent articles
    non_existent_numbers = [int(num) for num in filter(is_number, failures)]
    LOG.info('Storing the following article numbers as non-existent: {}'.format(non_existent_numbers))
    append_write_known_numbers_to_config(
            config_path, CONFIG_FILE_SECTION_ARTICLES, CONFIG_FILE_KEY_NONEXISTENT,
            non_existent_numbers)
