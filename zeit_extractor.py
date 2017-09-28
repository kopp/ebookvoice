#!/usr/bin/python


'''
Extract articles from Die Zeit epub, store them as plain text, one article per file.
Optionally sort the articles by resort by prefixing them with a running number.
'''

import xml.etree.ElementTree as ET
import re
import argparse
import os.path
import os
import subprocess
import logging
import shutil
import glob
from difflib import SequenceMatcher as SM



# Use this list to set the default order of all resorts.
# they only need to fuzzy match, see
RESORTS_ORDER = [
    'Politik',
    'Wissen',
    'Doktor',
    'Seite 1',
    'Recht und Unrecht',
    'Wirtschaft',
    'Dossier',
    'Geschichte',
    'Chancen',
    'Glauben und Zweifeln',
    'geld-spezial',
    'zeitmagazin',
    'ZEIT magazin',
    'Krimi Spezial',
    'Chancen Spezial',
    'Reisen',
    'reisen spezial',
    'Kultursommer',
    'Feuilleton',
    'Musik-Spezial',
    'Literatur-Spezial',
    'leserbriefe',
    'Zeit zum Entdecken',
    'Krimi Spezial',
    'ZEIT der Leser',
    'Kinder und Jugendbuch',
    'Olympia',
    'Hamburg',
    'Schweiz',
    'Oesterreich',
    'ZEIT im Osten',
    'Leo',
    'Kinderzeit',
    'Fussball',
    ]

RESORT_ORDER_MATCH_TRESHOLD = 0.75

# Use this list to define some resorts to skip in any case.
RESORTS_BLACKLIST = [
    'Golfen',
    'Hamburg',
    'Schweiz',
    'Oesterreich',
    'ZEIT im Osten',
    'Kinderzeit',
    'Fussball',
    'Feuilleton',
    'Leo - ZEIT fuer Kinder',
        ]

RESORT_BLACKLIST_MATCH_TRESHOLD = 0.8


class Article():
    '''Class to parse/process one article.'''

    def __init__(self, article_id=0):
        '''Initialize fields to None, set the article's ID.'''
        self._id = article_id
        self._resort = None
        self._title = None
        self._subtitle = None
        self._author = None
        # list of strings, each one paragraph
        self._content = None
        # True, if the article has a zeit.de/audio link
        self._hasaudio = None
        self._order_number = None


    def get_resort(self):
        return self._resort


    def set_number(self, number):
        self._order_number = int(number)


    def parse(self, xhtml_file_name):
        '''Parse one article from one xhtml file.'''
        logging.debug('Processing file {}'.format(xhtml_file_name))
        tree = ET.parse(xhtml_file_name)
        root = tree.getroot()

        # generate a namespaces dictionary
        # Without this, every html element would have to be prefixed with the
        # namespace-url, e.g.
        #   root.findall('.//{http://www.w3.org/1999/xhtml}div')
        # findall accepts a second argument, which is a dictionary with
        # namespaces shorthands.
        # This is actually documented in the element tree api, see
        # https://docs.python.org/2/library/xml.etree.elementtree.html#parsing-xml-with-namespaces
        namespaces = {'html': 'http://www.w3.org/1999/xhtml'}

        # Note: When checking whether a find() call found something, you _need_
        #       to compare the result to None.  Findings that have no children
        #       evaluate to False.  See
        #       https://stackoverflow.com/questions/20129996

        # title
        title = root.find('.//html:div[@class="article_titles"]/html:h1[@class="title"]', namespaces)
        if title is not None and title.text is not None:
            self._title = title.text
        else:
            # search for a supertitle
            supertitle = root.find('.//html:div[@class="article_titles"]/html:h3[@class="supertitle"]', namespaces)
            if supertitle is not None and supertitle.text is not None:
                logging.debug('Using supertitle as title in file {}'.format(xhtml_file_name))
                self._title = supertitle.text
            else:
                # search for a subheadline
                subheadline = root.find('.//html:div[@class="article_text"]//html:div[@class="subheadline-1 "]', namespaces)
                if subheadline is not None and subheadline.text is not None:
                    logging.debug('Using subheadline as title in file {}'.format(xhtml_file_name))
                    self._title = subheadline.text
                else:
                    # look for <title> in <head>
                    title_head = root.find('.//html:head/html:title', namespaces)
                    if title_head is not None and title_head.text is not None:
                        logging.debug('Using title from head as title in file {}'.format(xhtml_file_name))
                        self._title = title_head.text
                    else:
                        self._title = Article.DEFAULT_TITLE
                        logging.info('File {} has neither title, nor supertitle nor subheadline, using default title "{}"'.format(xhtml_file_name, self._title))

        # subtitle
        subtitle = root.find('.//html:div[@class="article_titles"]/html:h3[@class="subtitle"]', namespaces)
        if subtitle is not None and subtitle.text is not None:
            self._subtitle = subtitle.text.strip()
            # force trailing period
            if not self._subtitle[-1] in ['.', '?', '!']:
                self._subtitle += '.'
        else:
            self._subtitle = ''
            logging.debug('Article in file {} does not have a subtitle.'.format(
                xhtml_file_name))

        # author
        author = root.find('.//html:div[@class="article_titles"]/html:span[@class="author"]', namespaces)
        author_text = None # will be converted later
        if author is not None and author.text is not None:
            author_text = author.text
        else:
            author = root.find('.//html:div[@class="article_text"]/html:div[@class="group"]/html:div[@class="additional-content"]/html:div[@class="x-zeit-box"]/html:p[@class="paragraph style-3"]', namespaces)
            if author is not None and author.text is not None:
                author_text = author.text
            else:
                author_text = ''
                # sometimes, the author is hidden in the subtitle (in capital case)
                if self._subtitle:
                    name = re.findall('([A-Z]{2,})', self._subtitle)
                    author_text = ' '.join(name)
        if not author_text: # unable to find an author
            logging.debug('Article in file {} does not have an author.'.format(xhtml_file_name))
        self._author = ' '.join(map(Article._capitalize_names, author_text.lower().split(' ')))

        # resort
        for link in root.findall('.//html:div[@class="article_navigation"]//html:span[@class="link"]', namespaces):
            match = Article.OVERVIEW_RESORT_RE.match(link.text)
            if match:
                self._resort = match.group(1)

        # content
        # TODO: There are short sentences, that are quoted from later parts of
        #       the text, in a
        #           div[@class="additional-content"]/div[@class="x-zeit-box"]
        #       Unfortunately, the same xml markup is used for other parts of
        #       the text that might be important and they are not marked
        #       specially.
        #       Something like
        #           './/html:div[@class="article_text"]//html:p[not(ancestor::html:div[@class="x-zeit-box"])]
        #       would be nice to limit the search to p's that are not part of
        #       the x-zeit-box (see
        #       https://www.w3schools.com/xml/xpath_axes.asp and
        #       https://stackoverflow.com/questions/17191971) but this does not
        #       seem to be supported by ElementTree
        #           SyntaxError: prefix 'ancestor' not found in prefix map
        self._content = list()
        for paragraph in root.findall('.//html:div[@class="article_text"]//html:p', namespaces):
            text = ''.join(paragraph.itertext())
            # skip empty paragraphs (links etc):
            if text:
                self._content.append(text)

        # has audio
        # by default, assume that there is no audio; only if there is a link
            # with the appropriate content, this is assumed to have audio
        self._hasaudio = False
        for link in root.findall('.//html:div[@class="article_text"]//html:a[@class="x-zeit-link-box"]', namespaces):
            # check that link is an audio link
            target = link.attrib['href']
            description = link.find('./html:span', namespaces).text
            if 'audio' in description and 'zeit.de/misc_static_files' in target:
                self._hasaudio = True


        self._check_fields()


    DEFAULT_TITLE = 'Ohne Titel'


    def _check_fields(self):
        '''Check fields; if any is None, warn and set it to empty string.'''
        if self._id is None:
            logging.warning('found NoneType in _id')
            self._id = 0
        if self._resort is None:
            logging.warning('found NoneType in _resort')
            self._resort = ''
        if self._title is None:
            logging.warning('found NoneType in _title')
            self._title = ''
        if self._subtitle is None:
            logging.warning('found NoneType in _subtitle')
            self._subtitle = ''
        if self._author is None:
            logging.warning('found NoneType in _author')
            self._author = ''
        if self._content is None:
            logging.warning('found NoneType in _content')
            self._content = list()
        if self._hasaudio is None:
            logging.warning('found NoneType in _hasaudio')
            self._hasaudio = False



    def has_audio(self):
        '''Returns True, if this article has a zeit.de/audio link.'''
        return self._hasaudio


    def get_meta(self, format_string='{art_id}_{resort}_{title}', subs_spaces='_', asciify=True):
        '''
        Return meta information of the article.

        :param str format_string: Supply a format string if necessary.  It may
        contain:
            * art_id
            * resort
            * title
            * subtitle
            * author
            * audio
            * number (order number)
        :param str subs_spaces: Substitute any spaces in the resulting string
        by the string given here.  Use None to not do any substitution.
        :param bool asciify: Set to true to encode the string in ascii and
        remove all other characters.
        '''
        formatted_string = format_string.format(
            art_id=self._id,
            resort=self._resort,
            title=self._title,
            subtitle=self._subtitle,
            author=self._author,
            audio=self._hasaudio,
            number=self._order_number)
        if subs_spaces is not None:
            formatted_string = re.sub(' ', subs_spaces, formatted_string)
        if asciify:
            formatted_string = Article._remove_non_ascii(formatted_string)
        return formatted_string


    def generate_filename(self):
        '''Generate file name from article.'''
        format_string = '{resort}_{title}_{art_id}.txt'
        if self._order_number is not None:
            format_string = '{number:03d}_' + format_string
        return self.get_meta(format_string=format_string, subs_spaces='-')



    @staticmethod
    def _remove_non_ascii(string, missing=''):
        '''
        Return a string with all non-ascii characters substituted removed.
        :param str missing: set this to any string that is used for unknown characters.
        '''

        def ascii_variant(match):
            '''Return an alternative representation if possible.'''
            try:
                return Article.UMLAUTS_TRANSLATION[match.group(0)]
            except KeyError:
                return ''

        return re.sub(r'[^a-zA-Z0-9_.-]', ascii_variant, string)


    UMLAUTS_TRANSLATION = { u'ä': 'ae',
                            u'ö': 'oe',
                            u'ü': 'ue',
                            u'Ä': 'Ae',
                            u'Ö': 'Oe',
                            u'Ü': 'Ue',
                            u'ß': 'ss' }



    def spell_numbers(self):
        '''Substitute the numbers with textual representations.'''
        # import only if necessary...
        import spokenNumbersDe
        for i in range(len(self._content)):
            self._content[i] = spokenNumbersDe.spell_numbers(self._content[i])


    def plain_text(self):
        '''Return article in plain Text without markup.'''
        return '\n\n'.join([
            self._resort,
            self._title,
            self._subtitle,
            self._author] + self._content)


    @staticmethod
    def _capitalize_names(word):
        '''Return the word capitalized, if it may belong to a name.'''
        if word in ['von']:
            return word
        else:
            return word.capitalize()


    def __str__(self):
        '''Generate string representation containing all information.'''
        return 'Resort: {}\nTitle: {}\nSubtitle: {}\nAuthor: {}\nAudio: {}\nContent:\n{}\n'.format(
                self._resort, self._title, self._subtitle, self._author,
                self._hasaudio, '\n'.join(self._content))


    OVERVIEW_RESORT_RE = re.compile(r'\[Übersicht (.+)\]')



class Newspaper():
    '''
    Handle multiple resorts, each with one or more articles.

    Member:
        * resorts:  dictionary resort -> list of articles in that resort
    '''

    def __init__(self):
        '''Initialize empty resorts.'''
        self.resorts = {}

    def append(self, article):
        if not article.get_resort() in self.resorts:
            self.resorts.update({article.get_resort(): list()})
        self.resorts[article.get_resort()].append(article)

    def get_resorts(self):
        '''Return list of all resorts.'''
        return list(self.resorts.keys())

    def number_articles(self, resort_order, match_treshold):
        '''
        Add a prefix-number to each article that sorts the resorts by number.

        If all went well, return None, otherwise return set of unnumbered
        resorts (i.e. resorts that are missing in resort_order).

        The article names are matched using fuzzy matching; if the score is
        above the treshold, they are `matched'.
        '''
        counter = 1
        numbered_res = set()
        for res in resort_order:
            resort_found = Newspaper._fuzzy_match(res, self.resorts, match_treshold)
            if resort_found:
                numbered_res.add(resort_found)
                logging.debug('resort {} gets number {}'.format(resort_found, counter))
                for art in self.resorts[resort_found]:
                    art.set_number(counter)
                counter += 1
        unnumbered_res = set(self.resorts.keys()).difference(numbered_res)
        if unnumbered_res:
            logging.warning('These resorts are not numbered: {}'.format(unnumbered_res))
            return unnumbered_res
        else:
            return None

    @staticmethod
    def _fuzzy_match(pivot, strings, treshold):
        '''
        Return the string from strings that matches pivot best.  If no match is
        found with a fuzzy match above the treshold, return None.
        '''
        def get_ratio(x):
            return SM(None, pivot, x).ratio()
        candidate = max(strings, key=get_ratio)
        if get_ratio(candidate) > treshold:
            return candidate
        else:
            return None


    def articles(self):
        '''yield all articles, ordered by resorts'''
        for articles in self.resorts.values():
            for article in articles:
                yield article





def make_temp_dir():
    '''
    Create a temporary directory.
    Return directory path or None (in case of an error).
    '''
    mktemp = subprocess.Popen(['mktemp', '-d'], stdout=subprocess.PIPE)
    created_dir, errors = mktemp.communicate()
    created_dir = created_dir.strip().decode('utf-8')
    if errors:
        logging.warning('mktemp had error "{}".'.format(errors.strip()))
    if not os.path.isdir(created_dir):
        return None
    else:
        logging.debug('Created temporary directory {}.'.format(created_dir))
        return created_dir



def parse_arguments_and_execute():
    '''Main function: Parse command line and do what's necessary.'''

    def quit_error(msg, returncode=ERR_GENERAL):
        '''Quit program with given error message and return code.'''
        print(msg)
        parser.print_help()
        raise SystemExit(returncode)

    parser = argparse.ArgumentParser(
            description='Extract all Zeit articles as plain text.',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('zeit_epub', metavar='zeit.epub', type=str, nargs=1,
            help='The Zeit newspaper in epub format.')
    parser.add_argument('-o', '--outdir', metavar='directory', type=str, nargs=1
            , default='.',
            help='Directory to put the articles into.')
    parser.add_argument('-a', '--audio', action='store_const', const=True,
            default=False, dest='output_audio',
            help='Use this flag to extract articles with audio on zeit.de/audio as well.')
    parser.add_argument('-k', '--keeptemp', action='store_const', const=True,
            default=False, dest='keep_temp',
            help='Do not remove but keep the temporary directory where the epub was extracted to.')
    parser.add_argument('-n', '--number', action='store_const', const=True,
            default=False, dest='number_output',
            help='Number the output files basing on resort.')
    parser.add_argument('-s', '--spell-numbers', action='store_const', const=True,
            default=False, dest='spell_numbers',
            help='Substitute textual numbers with their spelled-out version.')
    parser.add_argument('-b', '--blacklist', action='store_const', const=True,
            default=False, dest='do_blacklist',
            help='Remove artivles that are in the (hard coded) black list.')
    parser.add_argument('--debug', action='store_const', dest='log_level',
            const=logging.DEBUG, default=logging.INFO,
            help='enable debug output')
    args = parser.parse_args()

    epub = args.zeit_epub[0]
    outdir = args.outdir[0]
    get_audio = args.output_audio
    keep_temp = args.keep_temp
    number_output = args.number_output
    spell_numbers = args.spell_numbers
    do_blacklist = args.do_blacklist
    log_level = args.log_level

    # set log level as one of the first things so that everything can use the
    # logger properly
    logging.basicConfig(level=log_level)

    if not os.path.isdir(outdir):
        # create it
        try:
            os.makedirs(outdir)
            logging.info('Created output directory "{}".'.format(outdir))
        except OSError:
            quit_error('output directory "{}" is invalid; unable to create it.'.format(
                outdir), ERR_OUT_INVALID)

    if not os.path.isfile(epub):
        quit_error('Unable to find file {}.\n'.format(epub))
    else:
        # create temporary directory
        created_dir = make_temp_dir()
        if created_dir is None:
            quit_error('Unable to create a temporary directory.', ERR_MKTEMP_FAILS)

        # unzip epub into that directory
        # do not view output
        dev_null = open(os.devnull, 'w')
        unzip_ret = subprocess.call(['unzip', epub, '-d', created_dir], stdout=dev_null)
        if unzip_ret not in [0, 1]:
            quit_error('unzip failed with error code {}'.format(unzip_ret), ERR_UNZIP)
        else:
            logging.debug('Unzipped content of epub to {}.'.format(created_dir))

        # parse each article, add it to a newspaper
        basedir = created_dir + '/OEBPS'
        paper = Newspaper()
        for resource in os.listdir(basedir):
            article_file = re.match(r'article_(\d+).xhtml', resource)
            if article_file:
                article = Article(int(article_file.group(1)))
                try:
                    filename = os.path.join(basedir, resource)
                    article.parse(filename)
                except ET.ParseError as e:
                    logging.error('xml parse error "{}" in {}; skipping that'.format(str(e), filename))
                    continue
                if spell_numbers:
                    article.spell_numbers()
                # consider audio articles only if requested
                if article.has_audio():
                    if get_audio:
                        logging.info('Using article {} that has audio on zeit.de'.format(article.get_meta()))
                    else:
                        logging.info('Skipping article {} that has audio on zeit.de'.format(article.get_meta()))
                        continue
                # skip article if in blacklist
                if do_blacklist:
                    if any((SM(None, article.get_resort(), resort).ratio() > RESORT_BLACKLIST_MATCH_TRESHOLD) for resort in RESORTS_BLACKLIST):
                        logging.info('Skipping article {} that is on blacklist'.format(article.get_meta()))
                        continue
                # append article to newspaper
                paper.append(article)

        # number articles by resort if requested
        if number_output:
            paper.number_articles(RESORTS_ORDER, RESORT_ORDER_MATCH_TRESHOLD)

        # write articles to file
        for article in paper.articles():
            try:
                with open(outdir + '/' + article.generate_filename(), 'w') as f:
                    f.write(article.plain_text())
            except PermissionError:
                quit_error('Not allowed to write to directory "{}".'.format(outdir), ERR_WRITE_PERM)

        # remove temporary directory
        if keep_temp:
            print('not removing temporary directory "{}".'.format(created_dir))
        else:
            logging.debug('removing temporary directory "{}".'.format(created_dir))
            shutil.rmtree(created_dir)



# error codes
ERR_NOERROR = 0
ERR_GENERAL = 1
ERR_MKTEMP_FAILS = 2
ERR_OUT_INVALID = 3
ERR_UNZIP = 4
ERR_WRITE_PERM = 5


if __name__ == '__main__':
    parse_arguments_and_execute()
    raise SystemExit(ERR_NOERROR)
else:
    logging.basicConfig(level=logging.INFO)
