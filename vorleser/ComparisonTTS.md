Comparison of different Tools and Web Services for TTS


# Web Services

(Quality is just a rough guess, tested with German.)

- http://www.voicerss.org/ quality 4, supports German, free plan sufficient for Zeit.
- https://www.naturalreaders.com/ Quality 4 not better than voicerss, free plan not sufficient.
- https://www.spokentext.net/ Short advert in each mp3 in free plan, need to set new account every 7 days
- https://www.ispeech.org/ quality 10, in free version add at the end, api available (testispeech@mailinator.com) -- allows only 10 words/50 chars in testing period.  Test page https://www.ispeech.org/create.text.to.speech.audio#packages takes input as GET and returns base64 decoded mpeg adts III (convert to mp3 using ffmpeg).
- http://www.yakitome.com/upload/from_text# quality 6, check api
- http://text-to-speech-translator.paralink.com/ quality 6, check api
- http://fromtexttospeech.com/ quality 7 (bettern than voicerss.org (more lively)), no api, but request to convert is a simple POST, the response contains the path/filename to a generated mp3.  Uses IVONA voices. quite slow (2.5 min for a Dossier of 5000 words -- voicerss takes about 25 sec).  Not that good comprehensible when sped up.
- http://ws.neospeech.com/ ok quality, plays music in background, check api, limited to 20 x 15 words / day
- https://responsivevoice.com quality 8, free for non-commercial use, GET request at https://responsivevoice.org/ returns base64 encoded mpeg adts III (convertible using ffmpeg) -- each get request is limited to roughly 100 characters.  The original webpage chops longer input at . or , which sounds bad because the voice is lowered a bit.


## collections of services

- https://www.technorms.com/980/top-10-web-based-services-for-text-to-speech-conversion (checked)
- https://stackoverflow.com/questions/7053334/text-to-speech-web-api (checked)



## Ruled out

- ImTranslator: translator not needed
- http://www.readthewords.com/ no German
- http://vozme.com no German
- odiogo: site seems down
- http://www.text2speech.org/ no German
- HearWho.com not recommended
- yakitome.com site seems down


