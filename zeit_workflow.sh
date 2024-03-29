#!/bin/bash


# parameter
AUDIO_RATE=2.3      # speedup factor
VORLESER_RATE=10    # arbitr units of vorleser
AUDIO_QUALITY=""    # defaults to empty; otherwise set to --quality <value>
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
    --no-audio              Do not process audio files, just process text
                            (requires --week).
    --no-text               Do not process text files, just process audio.
    --separate-folders      Use separate folders for selfmade/official audio.
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
# whether to process audio
do_process_audio=true
# whether to process text
do_process_text=true
# use separate folders for the two different kinds of audio
output_to_separate_folders=false


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
                    AUDIO_QUALITY="--quality 2"
                    VORLESER_QUALITY="--format 32khz_16bit_mono"
                    ;;
                (*)
                    echo Error: Unknown profile $profile
                    usage
                    exit $EXIT_UNKNOWN_OPTION
                    ;;
            esac

            ;;
        (--list-profiles)
            echo "profile       description"
            echo "quality       slightly higher quality (bitrate) with larger size"
            shift 1
            exit 0
            ;;
        (--no-audio)
            do_process_audio=false
            shift 1
            ;;
        (--no-text)
            do_process_text=false
            shift 1
            ;;
        (--separate-folders)
            output_to_separate_folders=true
            shift 1
            ;;
        (-w|--week)
            week=$2
            week_padded=$(printf "%02d" $week)
            shift 2
            ;;
        (--year)
            year=$2
            shift 2
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
    if ! ls DZ_20??-*.zip >/dev/null 2>/dev/null
    then
        echo Error: Unable to determine year/week number from files
        usage
        exit $EXIT_MISSING_INPUT_FILE
    fi

    # get file names
    # make sure to find only one file (-quit exits after first found file)
    zip_file_loc=$(find . -name 'DZ_20??-*.zip' -print -quit)
    week_padded=$(echo $zip_file_loc | sed 's/.*DZ_20..-\(.*\).zip/\1/')
    # remove trailing zero from zip file week
    week=$(echo $week_padded | sed 's/0\(.\)/\1/')
    year=$(echo $zip_file_loc | sed 's/.*DZ_20\(..\)-.*.zip/\1/')
    debug found release to be 20$year - $week
fi

# determine output folder name
output_folder=zeit_${week_padded}_audio


## audio processing
if $do_process_audio
then
    # get absolute path
    zip_file=$(readlink -f DZ_20${year}-${week_padded}.zip)

    # make sure that the file exist
    if [ ! -f $zip_file ]
    then
        echo Error: missing zip input file $zip_file
        usage
        exit $EXIT_MISSING_INPUT_FILE
    fi

    # unzip and downsample mp3s
    audio_dir=$output_folder
    mkdir $audio_dir
    pushd $audio_dir
    unzip $zip_file
    find . -name \*.mp3 -exec downsample_mp3 --rate $AUDIO_RATE $AUDIO_QUALITY {} \;
    # if in one folder, prefix with 001_ to sort them correctly
    # Note: GNU find does not work here, as it prefixes every filename with `./`
    #       and somehow -execdir and basename don't seem to work...
    if ! $output_to_separate_folders
    then
        for f in *.mp3
        do
            mv -v $f 001_${f}
        done
    fi
    popd
fi


## text processing
if $do_process_text
then
    # get absolute paths
    epub_file=$(readlink -f die_zeit?20${year}?${week_padded}*.epub)

    # make sure that the files exist
    if [ ! -f $epub_file ]
    then
        echo Error: missing epub input file $epub_file
        usage
        exit $EXIT_MISSING_INPUT_FILE
    fi


    # extract and read texts
    if $output_to_separate_folders
    then
        selfmade_dir=${output_folder}_selfmade
    else
        selfmade_dir=$output_folder
    fi
    mkdir -p $selfmade_dir
    pushd $selfmade_dir
    zeit_extractor -k -n -s -b $epub_file
    # deprecated:
    # find . -name \*.txt -exec vorleser --rate $VORLESER_RATE $VORLESER_QUALITY {} \;
    # default
    # find . -name \*.txt -exec vorleser --rate $VORLESER_RATE $VORLESER_QUALITY {} \;
    # default make based
    # Note: make allows to easily re-run until all files are processed
    echo "all: $(ls *.txt | sed 's,$,.mp3 \\,')" > Makefile
    echo "" >> Makefile
    echo "%.txt.mp3: %.txt" >> Makefile
    echo -e "\tazure_vorleser --voice de-DE-Stefan-Apollo --rate $AUDIO_RATE $<" >> Makefile
    while ! make all
    do
        echo "Error in reading stuff -- retrying"
    done

    popd
fi


echo Done.  Used folders $audio_dir and $selfmade_dir
