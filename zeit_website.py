"""
Access website of ``Die ZEIT`` and download ebook (EPUB) and audio files (MP3)
and determine, which articles are available as audio files.
"""

import datetime
import os
import pathlib
import json
import logging
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver

logger = logging.getLogger(__name__)

# path to a serialized cookie to login
# this was obtained via:
# - `driver.get("https://epaper.zeit.de/abo/diezeit/")`
# - enter email/password
# - `driver.get_cookies()` and store the result
LOGIN_COOKIE_FILE = pathlib.Path("~/.config/zeit_extractor/zeit_de_login_cookie.json").expanduser()


def make_firefox_options(download_dir: pathlib.Path) -> webdriver.FirefoxOptions:
    """
    Make options object to configure firefox to
    - directly download files (instead of asking the user what to do)
    - placing the downloads into a specified folder
    """
    options = webdriver.FirefoxOptions()
    # see https://stackoverflow.com/a/36309735/2165903
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", str(download_dir.absolute()))
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.download.viewableInternally.enabledTypes", "")
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/epub+zip;application/zip")
    options.set_preference("pdfjs.disabled", True)
    # Do not show/display the browser.
    options.headless = True
    return options


def _login(driver: webdriver.Firefox) -> None:
    driver.get("https://epaper.zeit.de/abo/diezeit/")

    with open(LOGIN_COOKIE_FILE, "r") as cookie_file:
        cookie = json.load(cookie_file)
    driver.add_cookie(cookie)

    driver.get("https://epaper.zeit.de/abo/diezeit/")


@dataclass
class IssueMetadata:
    issue: int
    year: int


_METADATA_RE = re.compile(r"DIE ZEIT (\d+)/(\d+)")


def _get_metadata(driver: webdriver.Firefox) -> IssueMetadata:
    driver.get("https://epaper.zeit.de/abo/diezeit/")
    current_issue_box = driver.find_element_by_css_selector("div.epaper-highlighted")
    metadata = current_issue_box.find_element_by_css_selector("p.epaper-info-title")
    match = _METADATA_RE.match(metadata.text)
    if match:
        issue_str, year_str = match.groups()
        issue = int(issue_str)
        year = int(year_str)
    return IssueMetadata(issue, year)


def _get_epub(driver: webdriver.Firefox) -> None:
    driver.get("https://epaper.zeit.de/abo/diezeit/")
    current_edition_link = driver.find_element_by_link_text("ZUR AKTUELLEN AUSGABE")
    current_edition_link.click()
    driver.find_element_by_link_text("EPUB FÜR E-READER LADEN").click()


def _get_audio(driver: webdriver.Firefox):
    driver.get("https://premium.zeit.de/abo/zeit-audio")
    driver.find_element_by_link_text("Alle Audios der aktuellen ZEIT als ZIP (MP3) herunterladen").click()


def _determine_audio_titles(driver: webdriver.Firefox, year: int, issue: int) -> list[str]:
    driver.get(
        f"https://premium.zeit.de/abo/zeit-audio?publication=DIE+ZEIT&year={year}&issue={issue}&ressort=all&op=Suche"
    )
    articles = driver.find_elements_by_css_selector("a.js-accordion-trigger")
    titles = [article.text for article in articles]
    return titles


def _find_file_by_extension(directory: pathlib.Path, extension: str) -> pathlib.Path:
    """
    Return the path to a file with given ``extension`` in the given
    ``directory``.
    The file has to exist and must be unique, otherwise this will raise
    ``ValueError``.
    """
    files = list(directory.glob("*." + extension.lstrip(".")))
    if len(files) != 1:
        raise ValueError(f"Expected exactly one .{extension} file in {directory} but found {len(files)}.")
    file = files[0]
    if not file.is_file():
        raise ValueError(f"{file} is not a file.")
    return file


def is_download_complete(path: pathlib.Path) -> bool:
    """
    Check, whether the download of the given file is complete.
    """
    if not path.exists():
        raise ValueError(f"Path {path} does not seem to be/get downloaded.")
    expected_part_file = path.parent / (path.name + ".part")
    return not expected_part_file.exists()


def wait_download_complete(path: pathlib.Path, timeout: datetime.timedelta | int = 120) -> None:
    """
    Sleep/block, while the given file is being downloaded.
    """
    if isinstance(timeout, int):
        timeout = datetime.timedelta(seconds=timeout)
    start = datetime.datetime.now()
    while not is_download_complete(path):
        if datetime.datetime.now() > start + timeout:
            raise TimeoutError(f"Waiting for download of {path} timed out after {timeout}.")
        time.sleep(1)


@dataclass
class ZeitIssue:
    """
    Metadata and paths to downloaded/downloading files to a Zeit issue.
    """

    metadata: IssueMetadata
    epub_file: Optional[pathlib.Path]
    audio_zip_file: Optional[pathlib.Path]
    audio_articles: list[str]


def get_current_zeit(
    *,
    target_directory: pathlib.Path = pathlib.Path("/tmp"),
    get_audio: bool = True,
    get_epub: bool = True,
) -> ZeitIssue:
    """
    Download epub and/or audio of the current issue to the given ``target_directory``.
    When this function returns, the data is not necessaritly downloaded
    completely; use one of the ``*_download_complete`` functions to make sure,
    that a download is complete.
    """
    options = make_firefox_options(target_directory)
    driver = webdriver.Firefox(options=options, service_log_path=os.path.devnull)

    _login(driver)

    metadata = _get_metadata(driver)

    if get_epub:
        logger.info(f"Obtaining epub file for {metadata.year}-{metadata.issue}.")
        _get_epub(driver)
        epub_file = _find_file_by_extension(target_directory, ".epub")
    else:
        epub_file = None

    if get_audio:
        logger.info(f"Obtaining zipped audio files for {metadata.year}-{metadata.issue}.")
        _get_audio(driver)
        audio_titles = _determine_audio_titles(driver, metadata.year, metadata.issue)
        audio_zip_file = _find_file_by_extension(target_directory, ".zip")
    else:
        audio_titles = []
        audio_zip_file = None

    return ZeitIssue(
        metadata=metadata,
        audio_articles=audio_titles,
        epub_file=epub_file,
        audio_zip_file=audio_zip_file,
    )


def main():
    """
    Download the current Zeit issue.
    """
    logging.basicConfig(level=logging.INFO)
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    issue = get_current_zeit(target_directory=temp_dir)
    print(issue)


if __name__ == "__main__":
    main()
