#!/usr/bin/env python

"""
Download the current articles of ``Die ZEIT`` website and turn them into audio
files.
"""

import pathlib
import tempfile
import difflib
import shutil
import warnings
import zipfile

from zeit_website import get_current_zeit, wait_download_complete
from zeit_extractor2 import StoredArticle, extract_articles, store_articles, load_options_from_config_file, Article


def _is_similar_string_contained(string: str, other_strings: list[str]) -> bool:
    return len(difflib.get_close_matches(string, other_strings)) != 0


def remove_if_matching_title(articles: list[Article], titles: list[str]) -> list[Article]:
    """Return all ``articles`` whose titles are not (close to) any of the passed ``titles``."""
    return [a for a in articles if not _is_similar_string_contained(a.title, titles)]


def _make_tts_makefile(stored_article: list[StoredArticle], directory: pathlib.Path):
    warnings.warn("Please use python instead of make!")
    path_to_makefile = directory / "Makefile-tts"
    with open(path_to_makefile, "w", encoding="utf-8") as makefile:
        makefile.write("all: ")
        for article in stored_article:
            makefile.write(f" {article.path}.mp3 ")
        makefile.write("\n\n")
        makefile.write("\n%.txt.mp3: %.txt\n")
        makefile.write("\tazure_vorleser --voice de-DE-Stefan-Apollo --rate 2.3 $<\n\n")
    print("Makefile available at ", path_to_makefile)

    path_to_script = directory / "make-tts.sh"
    with open(path_to_script, "w", encoding="utf-8") as script:
        script.write("#!/usr/bin/env bash\n\n")
        script.write(f"while ! make -f {path_to_makefile.name} \ndo\n  echo retry\ndone\n\n")
    print("Build script available at ", path_to_script)


def _make_audio_makefile(audio_files: list[pathlib.Path], directory: pathlib.Path):
    warnings.warn("Please use python instead of bash!")

    path_to_script = directory / "make-audio.sh"
    with open(path_to_script, "w", encoding="utf-8") as script:
        script.write("#!/usr/bin/env bash\n\n")
        for audio_file in audio_files:
            script.write(f"downsample_mp3 --rate 2.3 {audio_file.name}\n")
    print("Build script available at ", path_to_script)


def main():
    """See ``__doc__``"""
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    print("Fetching the current Zeit issue.")
    current_zeit = get_current_zeit(target_directory=temp_dir)
    print(current_zeit)
    shutil.copy(
        current_zeit.epub_file,
        pathlib.Path("/tmp") / f"die_zeit_{current_zeit.metadata.year}-{current_zeit.metadata.issue:02}.epub",
    )
    output_path = pathlib.Path("/tmp") / f"zeit_{current_zeit.metadata.year}-{current_zeit.metadata.issue:02}"
    output_path.mkdir()

    storage_options = load_options_from_config_file("~/.config/zeit_extractor/options.conf")
    all_articles = extract_articles(current_zeit.epub_file)
    unknown_ressorts, stored_articles = store_articles(all_articles, output_path, storage_options)
    stored_articles_without_audio = remove_if_matching_title(stored_articles, current_zeit.audio_articles)
    _make_tts_makefile(stored_articles_without_audio, output_path)
    if len(unknown_ressorts) > 0:
        print("Please add the following ressorts to the configuration file:\n - ", "\n - ".join(unknown_ressorts))

    wait_download_complete(current_zeit.audio_zip_file)
    audio_files = []
    with zipfile.ZipFile(current_zeit.audio_zip_file, "r") as audio_zip:
        zipped_filenames = audio_zip.namelist()
        for zipped_filename in zipped_filenames:
            extracted_filename = pathlib.Path(audio_zip.extract(zipped_filename, path="output_path"))
            audio_file = shutil.move(extracted_filename, output_path / f"001_{extracted_filename.name}")
            audio_files.append(audio_file)
    _make_audio_makefile(audio_files, output_path)


if __name__ == "__main__":
    main()
