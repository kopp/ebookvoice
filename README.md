# ebookvoice
Tools to extract plain text from ebooks and read it out loud.

## zeit_extractor

Download the Die Zeit epub and run this script on it.  It will extract all articles and write them as plain text file.

Some of the settings (such as whitelist of resorts) are currently hardcoded -- i.e. they have to be modified in the script.


## mpf_extractor

This tool generates plain text files from the articles of the Max Planck Forschung found under https://bc-v2.pressmatrix.com/de/profiles/b3b32e362f93/editions.


## vorleser

Tools to generate mp3 files from the plain text.
The tool using the service from www.voicerss.org does a better job, but requires internet connection.


# Workflow

My workflow is usually:

- download new Die Zeit epub
- then
```bash
zeit_extractor -k -n -s -b ../die_zeit-2016-20_0.epub
for f in *.txt
do
  vorleser --rate 8 $f
done
```
