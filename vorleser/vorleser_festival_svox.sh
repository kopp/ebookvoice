#!/usr/bin/bash


function usage()
{
    cat<<EOF
    Use speech synthesis to generate an audio file from text input.

    usage: $0 [OPTIONS] infile [outfile]

    infile: a text input file
    outfile: an audio output file; if it has no extension, WAV is assumed,
        otherwise the extension determines the format (ffmpeg and sox are used
        for the conversion).  If none given: infile - .txt + .mp3.

    OPTIONS:
        --module <name>     Select a synthesizer module. Currently known:
                                - ims1, ims2, ims3, ims4: festival with IMS
                                    extension using mbrola voices de{1-4}
                                - pico: using SVOX pico
        --params <string>   Parameters that are passed to the tool (text2wave
                            or pico2wave, depending on module).
        -h, --help          Show this help and exit
EOF
}



# default settings
module="ims4"
params=""
infile="INFILE_UNSET"
outfile="OUTFILE_UNSET"
prefered_encoding="iso-8859-1"

# parse command line arguments
while [ ! -z "$1" ]
do
    case $1 in
        ("--module")
            module=$2
            shift 2
            ;;
        ("--params")
            params=$2
            shift 2
            ;;
        ("-h" | "--help")
            usage
            exit 0
            ;;
        (*)
            if [ $infile = "INFILE_UNSET" ]
            then
                infile=$1
                shift
                if [ ! -f $infile ]
                then
                    echo "error: infile '$infile' is no input file."
                    usage
                    exit 1
                fi
            else
                outfile=$1
                shift
            fi
    esac
done


# determine outfile name
# NOTE: this has to happen before a temporary input file is created.
if [ $outfile = "OUTFILE_UNSET" ]
then
    outfile=$(dirname $infile)/$(basename $infile .txt).mp3
    echo "determining outfile $outfile"
fi


# if the encoding of the infile is not iso-8859-1, convert it to that
encoding=$(file -bi $infile | sed 's/.*charset=\([-a-zA-Z0-9_]\+\);\?.*/\1/')
if [ ! $encoding = $prefered_encoding ]
then
    temp_infile=$(mktemp --suffix=.txt)
    # NOTE: this discards characters that cannot be converted
    iconv -c -f $encoding -t $prefered_encoding $infile > $temp_infile
    infile=$temp_infile
else
    temp_infile=""
fi


# if the outfile is no wave file, use a temporary file
if echo $outfile | grep -q '.wav$'
then
    temp_outfile=$outfile
else
    temp_outfile=$(mktemp --suffix=.wav)
fi


# execute generation
echo "starting generation from $infile to $temp_outfile"
case $module in
    ("ims1" | "ims2" | "ims3" | "ims4")
        num=$(echo $module | sed 's/ims\([1-4]\)/\1/')
        text2wave -o $temp_outfile -eval "(voice_german_de${num}_os)" $infile
        ;;
    ("pico")
        pico2wave --lang=de-DE --wave="${temp_outfile}" "$(cat $infile)"
        ;;
    (*)
        echo "error: module '$module' unknown."
        usage
        exit 2
esac


# change outfile format if necessary
if [ ! $temp_outfile = $outfile ]
then
    echo "converting audio file from $temp_outfile to $outfile"
    echo "CHANGING VOLUME LEVEL FIVE FOLD"
    ffmpeg -i $temp_outfile -af "volume=5.0" $outfile
    rm $temp_outfile
fi


# clean up temp infile (if necessary)
if [ ! -z $temp_infile ]
then
    rm $temp_infile
fi
