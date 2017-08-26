#!/bin/bash

base_url=https://code.responsivevoice.org/getvoice.php

function usage()
{
    cat<<EOF
Return text from a text file read out as mp3, using $base_url.

Usage:
    $0 <input file> <output filename>
EOF
}

if [ -z "$1" ] || [ -z "$2" ]
then
    usage
    exit 1
fi

in_file=$1
out_file=$2
limit_characters=100

if [ $(wc -m $in_file | awk '{ print $1 }') -gt $limit_characters ]
then
    cat<<EOF
This service only supports input files with less than $limit_characters
characters.  You can try to split the text up into smaller files.
Unfortunately, the voice acts like the end of a smaller file was the end of a
sentence, so it sounds strange, when concatenating the outputs...
EOF
    exit 2
fi


#GET request with data formatted by curl
# Note: POST does not work.
curl --get \
    --output $out_file \
    --data-urlencode  "t=$(cat $in_file)" \
    --data-urlencode "tl=de" \
    --data-urlencode "sv=" \
    --data-urlencode "vn=" \
    --data-urlencode "pitch=0.5" \
    --data-urlencode "rate=0.5" \
    --data-urlencode "vol=1" \
    $base_url
