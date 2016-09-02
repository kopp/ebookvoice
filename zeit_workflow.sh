#!/bin/bash


# parameter
AUDIO_RATE=1.9      # speedup factor
VORLESER_RATE=8     # arbitr units of vorleser
AUDIO_QUALITY=""    # defaults to empty; otherwise set to --bitrate <value>
VORLESER_QUALITY="" # defaults to empty; otherwise set to --format <format>

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
                    exit 2
                    ;;
            esac

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
            exit 1
            ;;
    esac
done



# actual program

# check dependencies
if ! which vorleser downsample_mp3 zeit_extractor
then
    echo Error: Unable to use the tool as dependencies are missing
fi

# check if files exist
if ! ls DZ_20??-*.zip die_zeit-20??-*.epub >/dev/null 2>/dev/null
then
    echo Error: input files not found
    usage
    exit 2
fi

# get file names
zip_file_loc=$(ls DZ_20??-*.zip)
week=$(echo $zip_file_loc | sed 's/DZ_20..-\(.*\).zip/\1/')
year=$(echo $zip_file_loc | sed 's/DZ_20\(..\)-.*.zip/\1/')
# get absolute paths
epub_file=$(readlink -f die_zeit-20${year}-${week}*.epub)
zip_file=$(readlink -f $zip_file_loc)
debug found release to be 20$year - $week

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
