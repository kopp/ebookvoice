#!/usr/bin/bash


DEBUG=false

function usage()
{
    cat<<EOF
$(basename $0) [OPTIONS] [<textfile> [<outfile>]]

Read the text in input file <textfile>, store output in <outfile>.

Uses api from voicerss.org -- internet connection required.

OPTIONS:
    <infile>            filename of the input file; may be - for stdin
                        (default)
    <outfile>           filename of the output file; defaults to
                        base of <infile> + .<output codec>, if -, outputs to
                        stdout (default)
    --codec <fmt>       one of mp3, wav, aac, ogg, caf
    --language <lan>    language code, e.g. en-us, de-de; see
                        http://www.voicerss.org/api/documentation.aspx
    --rate <rt>         speech rate, between -10 (slowest) and 10 (fastest),
                        defaults to 1
    --format <fmt>      format; quality format like <spl>khz_<bit>bit_<sur>
                            <spl>: 8, 11, 12, 16, 22, 24, 32, 44, 48
                            <bit>: 8, 16
                            <sur>: mono, stereo
                        default: 24khz_16bit_mono
    --debug             run in debug mode (more verbose output)
    -h, --help          show this help and exit

EOF
}

# directory where script is stored
# see http://stackoverflow.com/questions/59895/can-a-bash-script-tell-what-directory-its-stored-in
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE" # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
done
bindir="$( cd -P "$( dirname "$SOURCE" )" && pwd )"

# voicerss api key
key=$(cat $bindir/voicerss_org_key)

# parameters; default values
input_file=_INPUT_UNSET_
output_file=_OUTPUT_UNSET_
language=de-de
rate=1
codec=MP3
format=24khz_16bit_mono

# parse command line arguments
while [ ! -z "$1" ]
do
    case $1 in
        ("-h" | "--help")
            usage
            exit 0
            ;;
        ("--debug")
            DEBUG=true
            shift
            ;;
        ("--codec")
            codec=$(echo $2 | tr '[:lower:]' '[:upper:]')
            shift 2
            ;;
        ("--language")
            language=$2
            shift 2
            ;;
        ("--rate")
            rate=$2
            shift 2
            ;;
        ("--format")
            format=$2
            shift 2
            ;;
        (*)
            if [ $input_file = _INPUT_UNSET_ ]
            then
                if [ $1 = "-" ]
                then
                    input_file=/dev/stdin
                    output_file=_OUTPUT_STDOUT_
                else
                    input_file=$1
                fi
            elif [ $output_file = _OUTPUT_UNSET_ ] || [ $output_file = _OUTPUT_STDOUT_ ]
            then
                if [ $1 = "-" ]
                then
                    output_file=/dev/stdout
                else
                    output_file=$1
                fi
            else
                echo "unable to parse positional parameter $1"
                usage
                exit 2
            fi
            shift
            ;;
    esac
done

# sanitize input
if [ -f $input_file ]
then
    # remove stuff that makes problems with the POST request
    text=$(sed -e 's/&/und/g' -e "s,\",',g" $input_file)
else
    echo error: input file not found
    usage
    exit 1
fi

case $output_file in
    ("_OUTPUT_UNSET_")
        output_file=$(basename $input_file .txt).$(echo $codec | tr '[:upper:]' '[:lower:]')
        ;;
    ("_OUTPUT_STDOUT_")
        output_file=/dev/stdout
        ;;
esac


# "status" output
echo reading file $input_file 
# by default, make curl silent
curl_silent_params="--silent"


if $DEBUG
then
    cat <<EOF
parameters used:
    infile:     $input_file
    outfile:    $output_file
    codec:      $codec
    rate:       $rate
    language:   $language
EOF

    curl_silent_params=""
fi


curl $curl_silent_params -o $output_file --data "key=$key&hl=$language&r=$rate&c=$codec&f=$format&src=$text" http://api.voicerss.org/?
