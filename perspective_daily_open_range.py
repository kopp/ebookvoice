#!/usr/bin/python

import argparse
import webbrowser

parser = argparse.ArgumentParser(description='Open a range of Perspective Daily articles in the web browser.\nUse this tool to log in to PD and then open a bunch of articles at once to later pass each one to perspective_daily_extractor.py')
parser.add_argument('begin_number', type=int,
                    help='first article to open')
parser.add_argument('end_number', type=int,
                    help='last article to open')

args = parser.parse_args()

# sanity checks
if args.begin_number > args.end_number:
    raise ValueError('Error: the beginning number should be smaller than the ending number')
else:
    print('Going to open articles from {} to {}'.format(args.begin_number, args.end_number))

for i in range(args.begin_number, args.end_number + 1):
    webbrowser.open('https://perspective-daily.de/article/{}'.format(i))
