#!/usr/bin/bash

# downsample mp3 file given on cmdline

# default values
in=""               # path to input file
outfile=_OVERWRITE_ # path to output file
rate=""             # speedup factor
quality=2           # 0 (best) to 9 (worst)
overwrite=true      # whether to overwrite the input with the output

# exit codes
EXIT_SUCCESS=0
EXIT_INPUT_NOT_FOUND=1
EXIT_MISSING_INPUT=2
EXIT_UNKNOWN_OPTION=4
EXIT_UNSUPPORTED_RATE=5

function usage()
{
    cat<<EOF
downsample one mp3 file

usage: $(basename $0) [options] file.mp3

Downsampled file has same name as input file.

Options:
    -k, --keep      Do not overwrite the input file, output in temp file
                    (default: do overwrite)
    --outfile val   Path to the output file (default: overwrite input)
    --rate val      Slow down/speed up audio; in [0.5 : 4.0] (default: nothing)
    --quality val   Set quality to use; see
                    https://trac.ffmpeg.org/wiki/Encode/MP3 (default: $quality).
EOF
}

while [ -n "$1" ]
do
    case "$1" in
        (-h|--help)
            usage
            exit $EXIT_SUCCESS
            ;;
        (-k|--keep)
            overwrite=false
            shift
            ;;
        (--rate)
            rate=$2
            shift 2
            ;;
        (--quality)
            quality=$2
            shift 2
            ;;
        (--outfile)
            outfile=$2
            shift 2
            ;;
        (*) # other arguments are input file
            if [ -z "$in" ]
            then
                in=$1
                shift
            else
                echo "Unknown option $1"
                usage
                exit $EXIT_UNKNOWN_OPTION
            fi
            ;;
    esac
done

if [ -z "$in" ]
then
    echo "error: supply an input file"
    usage
    exit $EXIT_MISSING_INPUT
else
    if [ ! -f $in ]
    then
        echo "error: unable to find input file $in"
        usage
        exit $EXIT_INPUT_NOT_FOUND
    fi
fi

if [ $outfile = _OVERWRITE_ ]
then
    out=$(mktemp --dry-run --suffix=.mp3)
else
    out="$outfile"
    overwrite=false
fi

# rate see
# https://trac.ffmpeg.org/wiki/How%20to%20speed%20up%20/%20slow%20down%20a%20video
rate_command=""
if [ -n "$rate" ]
then
    rate_command=""
    # atempo works only with values between 0.5 and 2
    # For more, use multiple atempo filters (atempo=2,atempo=1.7) for speedup
    # 3.4 (= 2 * 1.7).
    if (( $( echo "0.5 <= $rate && $rate <= 2" | bc -l ) ))
    then
        rate_command="-filter:a atempo=${rate}"
    elif (( $( echo "2 < $rate && $rate <= 4" | bc -l ) ))
    then
        half_rate=$(echo "scale=2; $rate / 2" | bc -l)
        rate_command="-filter:a atempo=2,atempo=$half_rate"
    else
        echo "Unsupported speedup rate $rate"
        exit $EXIT_UNSUPPORTED_RATE
    fi

    echo "using rate command $rate_command"
fi

ffmpeg -i $in $rate_command -acodec libmp3lame -qscale:a $quality $out

if $overwrite
then
    mv $out $in
else
    echo "Output is in file $out"
fi
