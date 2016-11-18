#!/bin/bash


# parameter
AUDIO_RATE=1.9      # speedup factor
VORLESER_RATE=8     # arbitr units of vorleser
AUDIO_QUALITY=""    # defaults to empty; otherwise set to --bitrate <value>
VORLESER_QUALITY="" # defaults to empty; otherwise set to --format <format>

# exit codes
EXIT_UNKNOWN_OPTION=1
EXIT_MISSING_DEPENDENCY=2
EXIT_MISSING_INPUT_FILE=3

function usage() {
    cat<<EOF
Zeit workflow: Generate mp3s from epub and zip for one week.

Usage:
    $(basename $0) [options]
    Execute this in the same folder where epub and mp3-zip (e.g.
    die_zeit-2016-30.epub and DZ_2016-30.zip) were downloaded to.

Options:
    --profile <profile>     Use a bunch of pre-configured settings (profile).
    --list-profiles         List all known profiles.
    -w --week <week>        Look for input files for the given week number
                            (by default determine the number from found files).
    --year <year>           Look for input files for given year -- only use
                            this if --week is used; defaults to the current
                            year (last two digits).

Note:
    Maybe you'll need to rename the files...
EOF
}



# use this for debug output messages
function debug() {
    echo $@
}


# profile: list of settings contained in one profile
profile=_NO_PROFILE_
# week issue number -- defaults to: look for it
week=_TO_BE_DETERMINED_
# last two digits of the year -- defaults to current year
year=$(date +%y)

# parse command line options
while [ -n "$1" ]
do
    case "$1" in
        (-h|--help)
            usage
            exit 0
            ;;
        (--profile)
            profile=$2
            shift 2

            # directly interpret profiles so that other options may overwrite the profile choices
            case "$profile" in
                (quality)
                    AUDIO_QUALITY="--bitrate 96"
                    VORLESER_QUALITY="--format 32khz_16bit_mono"
                    ;;
                (*)
                    echo Error: Unknown profile $profile
                    usage
                    exit $EXIT_UNKNOWN_OPTION
                    ;;
            esac

            ;;
        (-w|--week)
            week=$2
            shift 2
            ;;
        (--year)
            year=$2
            shift 2
            ;;
        (--list-profiles)
            echo "profile       description"
            echo "quality       slightly higher quality (bitrate) with larger size"
            shift 1
            exit 0
            ;;
        (*)
            echo Error: Unknown option $1
            usage
            exit $EXIT_UNKNOWN_OPTION
            ;;
    esac
done



# actual program

# check dependencies
if ! which vorleser downsample_mp3 zeit_extractor > /dev/null
then
    echo Error: Unable to use the tool as dependencies are missing
    exit $EXIT_MISSING_DEPENDENCY
fi


# if no week is given, get it from found file names
if [ $week = _TO_BE_DETERMINED_ ]
then
    # check if files exist
    if ! ls DZ_20??-*.zip die_zeit-20??-*.epub >/dev/null 2>/dev/null
    then
        echo Error: Unable to determine year/week number from files
        usage
        exit $EXIT_MISSING_INPUT_FILE
    fi

    # get file names
    # make sure to find only one file (-quit exits after first found file)
    zip_file_loc=$(find . -name 'DZ_20??-*.zip' -print -quit)
    week=$(echo $zip_file_loc | sed 's/DZ_20..-\(.*\).zip/\1/')
    year=$(echo $zip_file_loc | sed 's/DZ_20\(..\)-.*.zip/\1/')
    debug found release to be 20$year - $week
fi

# get absolute paths
epub_file=$(readlink -f die_zeit-20${year}-${week}*.epub)
zip_file=$(readlink -f DZ_20${year}-${week}.zip)

# make sure that the files exist
if [ ! -f $epub_file ]
then
    echo Error: missing epub input file $epub_file
    usage
    exit $EXIT_MISSING_INPUT_FILE
fi
if [ ! -f $zip_file ]
then
    echo Error: missing zip input file $epub_file
    usage
    exit $EXIT_MISSING_INPUT_FILE
fi

# unzip and downsample mp3s
audio_dir=zeit_${week}_audio
mkdir $audio_dir
pushd $audio_dir
unzip $zip_file
find . -name \*.mp3 -exec downsample_mp3 --rate $AUDIO_RATE $AUDIO_QUALITY {} \;
popd

# extract and read texts
selfmade_dir=zeit_${week}_selfmade
mkdir $selfmade_dir
pushd $selfmade_dir
zeit_extractor -k -n -s -b $epub_file
find . -name \*.txt -exec vorleser --rate $VORLESER_RATE $VORLESER_QUALITY {} \;
popd


echo Done.  Used folders $audio_dir and $selfmade_dir
