#!/usr/bin/python

# get data from net
import urllib.request

# parse data
import re
# hash texts to check if it's new or already parsed
import hashlib

# logging
import logging
import sys

# file system: write .txt files to folder
import os.path

# command line
import argparse
import webbrowser



# logging
LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler(sys.stdout))
#LOG.setLevel(logging.DEBUG)



# statics
# find a link to a text content page
TEXT_LINK_RE = re.compile(r'<a class="fancybox" data-fancybox-type="iframe" data-fancybox-autosize="true" onclick=".*" href="(.*)"></a>')
# find content of a text page -- stuff nested in the body
TEXT_CONTENT_RE = re.compile(r'<body>(.*)</body>')
# find a headline in the body of text content (h1 or h2)
TEXT_CONTENT_HEADLINE_RE = re.compile(r'<h([12])>(.*?)</h\1>')

ENCODING = 'utf-8'
WEB_BASE = 'https://bc-v2.pressmatrix.com'
SELECTION_PAGE = WEB_BASE + '/de/profiles/b3b32e362f93/editions'


def get_web_text(link):
    '''
    Return text content from given link.
    :return str: request answer in one big string
    '''
    # generate Request
    req = urllib.request.Request(
            link,
            headers={'User-Agent': "Mozilla/5.0 (X11; Linux x86_64; rv:45.0) Gecko/20100101 Firefox/45.0"})
    # send Request
    with urllib.request.urlopen(req) as response:
        html = response.read()
        text = html.decode(ENCODING)
        return text



class Text():
    '''
    Represent one Text in a MPF magazine.
    '''
    def __init__(self, text_link):
        self._content = None
        self._headline = None
        self._hash_value = None # cache value
        html = get_web_text(text_link)
        match = TEXT_CONTENT_RE.search(html)
        if match:
            self._content = match.group(1)
            h_match = TEXT_CONTENT_HEADLINE_RE.search(self._content)
            if h_match:
                self._headline = h_match.group(2)

    def get_hash(self):
        '''
        Return md5 hex hash of content (without html tags or spaces)
        '''
        if not self._hash_value:
            checksum = hashlib.md5()
            text = re.sub(r'<.+?>', '', self._content)
            text = re.sub(r'\s', '', text)
            checksum.update(text.encode())
            self._hash_value = checksum.hexdigest()
        return self._hash_value

    def get_headline(self):
        '''
        Return the headline
        '''
        return self._headline

    def get_content_txt(self):
        '''
        Return the content of the article as one big string with newlines.
        '''
        cont = self._content
        # newlines after heading
        cont = Text._subst_tag('h[12]', '', cont)
        cont = Text._subst_tag('/h[12]', '\n\n\n', cont)
        # substitute newlines
        cont = Text._subst_tag('br', '\n\n', cont)
        cont = Text._subst_tag('/p', '\n\n', cont)
        cont = Text._subst_tag('p', '', cont)
        # remove all other html tags
        cont = Text._subst_tag('.*?', '', cont)
        return cont

    @staticmethod
    def _subst_tag(tag, repl, string):
        '''
        Remove tag with surrounding spaces from string.
        '''
        return re.sub(r' *<{}> *'.format(tag), repl, string)


    def is_article(self):
        '''
        Return True iff the text is a `proper' article (i.e. not a caption etc.)
        '''
        return (self._headline is not None and len(self._headline) > 2) and ((len(self._content) - len(self._headline)) > 30)

    def __str__(self):
        if self._headline:
            return '{} ({})'.format(self._headline, self.get_hash()[0:6])
        else:
            if self._content:
                return 'Unknown headline; content begins with {}'.format(self._content[0:50])
            else:
                return 'Empty text'


class Magazine():
    '''
    Represent one MPF magazine.
    '''
    def __init__(self, base_link):
        # all texts in this magazine
        self._texts = []
        # the hashes of the texts -- use this set to check, whether a certain
        # text is already in _texts.
        self._text_hashes = set()
        self._parse_magazine(base_link)


    def _parse_magazine(self, base_link):
        '''
        Iterate over pages in the magazine and get all texts.
        '''
        LOG.info('Going to parse all pages of magazine at {}'.format(base_link))
        for page_num in range(1, 500):
            try:
                self._parse_page(base_link + '/pages/page/{}'.format(page_num))
                LOG.info('  Page {:3} done, currently {:3} articles'.format(page_num, len(self._texts)))
            except urllib.error.HTTPError as ex:
                if str(ex).strip() == 'HTTP Error 500: Internal Server Error':
                    LOG.debug('page behind last page is number {}'.format(page_num))
                    break
        LOG.info('Found {} articles in the magazine'.format(len(self._texts)))


    def _parse_page(self, base_link):
        '''
        Parse one page.
        '''
        LOG.debug('Going to look for page {}'.format(base_link))
        html = get_web_text(base_link)
        # parse answer
        # Note: unfortunately, it's not possible to use xml.etree.ElementTree
        #       because the html is not xml well-formed :-(
        #root = ET.fromstring(html)
        #root.findall('.//a[@class="fancybox" and @data-fancybox-type="iframe" and @data-fancybox-autosize="true" and @href]')
        # parse using regexp
        for line in html.split('\n'):
            match = TEXT_LINK_RE.search(line.strip())
            if match:
                text_link = WEB_BASE + match.group(1)
                text = Text(text_link)
                if text.is_article():
                    text_hash = text.get_hash()
                    LOG.debug('Found text {}'.format(text))
                    if text_hash not in self._text_hashes:
                        LOG.debug('Text is new; adding it to the magazine.')
                        self._texts.append(text)
                        self._text_hashes.add(text_hash)


    def to_txt(self, folder):
        '''
        Generate .txt files from each article to the given folder.
        :param folder str: path to a folder where to put the .txt files.
        '''
        abspath_dir = os.path.abspath(folder)
        if os.path.isdir(abspath_dir):
            counter = 0
            for text in self._texts:
                counter += 1
                title_clean = re.sub(r'[^\w]', '', re.sub(r'\s+', '_', text.get_headline()))
                filename = '{:03}_{}.txt'.format(counter, title_clean)
                path = os.path.join(abspath_dir, filename)
                LOG.debug('Writing text {} to file {}'.format(text, path))
                with open(path, 'w') as txt_file:
                    txt_file.write(text.get_content_txt())
        else:
            LOG.error('Unable to generate .txt files to folder {} ({}) which was not found.'.format(folder, abspath))




def magazine_to_txt_files(base_address, directory):
    '''
    Get all texts from the given base address and generate text files under directory.
    '''
    if not os.path.isdir(directory):
        LOG.info('Creating directory {}'.format(directory))
        os.makedirs(directory)
        if not os.path.isdir(directory):
            LOG.fatal('Unable to create directory {} (target for txt files).'.format(directory))
            raise SystemExit(1)
    if not re.search(WEB_BASE, base_address):
        LOG.fatal('Web base address is hard coded to {} and differs from {}'.format(
            WEB_BASE, base_address))
        raise SystemExit(2)
    mag = Magazine(base_address)
    mag.to_txt(directory)


def open_browser_selection():
    '''
    Open browser at selection page.
    '''
    webbrowser.open(SELECTION_PAGE)


# main entry point
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download MaxPlanckForschung texts')
    parser.add_argument('base_address', type=str,
            help='Base address of the MPF issue.  You get this by selecting an issue on {} and then copy the address.  Type "help" here to open firefox to go to the selection page.'.format(SELECTION_PAGE))
    parser.add_argument('--out-type', '-t', type=str, required=False,
            dest='out_type', default='txt',
            help='Type in which to store the MPF issue.')
    parser.add_argument('--out-dir', '-o', type=str, required=False,
            dest='out_dir', default='/tmp/MPF',
            help='Directory where to store the output files.')
    parser.add_argument('--debug',
            action='store_const', dest='debug', const=True, default=False,
            help='Give verbose (debug) output.')
    args = parser.parse_args()

    if args.debug:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)

    if args.base_address == 'help':
        open_browser_selection()
        raise SystemExit

    if args.out_type == 'txt':
        magazine_to_txt_files(args.base_address, args.out_dir)
    else:
        LOG.fatal('Unknown output format {}'.format(args.out_type))
        raise SystemExit(3)
