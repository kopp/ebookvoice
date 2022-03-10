"""
Extract the articles from a "Die Zeit" EPUB in plain text.
"""

import difflib
import tempfile
import pathlib
import re
import argparse
import zipfile
import configparser
from dataclasses import dataclass, field, asdict
from typing import Iterable

from bs4 import BeautifulSoup


# API

DEFAULT_CONFIG_FILE_PATH = pathlib.Path("~/.config/zeit_extractor/options.conf").expanduser().absolute()


@dataclass(frozen=True)
class Article:
    """Content of a single article."""

    title: str
    ressort: str
    content: str


def extract_article(xhtml_file_path: pathlib.Path) -> Article:
    """Extract a single article from its xhtml file."""
    with open(xhtml_file_path, "r") as xhtml_file:
        soup = BeautifulSoup(xhtml_file, "html.parser")
        title = soup.title.text
        return Article(
            title=title,
            ressort=_find_ressort(soup),
            content=_find_content(soup),
        )


def extract_articles(epub_file_path: pathlib.Path) -> list[Article]:
    """Extract all articles from an epub file."""
    articles: list[Article] = []
    with tempfile.TemporaryDirectory() as unzip_folder:
        articles_files = _extract_epub(epub_file_path, pathlib.Path(unzip_folder))
        for article_file in articles_files:
            articles.append(extract_article(article_file))
    return articles


def write_article_to_file(article: Article, file_path: pathlib.Path):
    """Write a single article to a (plain) text file (UTF-8 with a BOM)."""
    with open(file_path, "w", encoding="utf-8-sig") as article_file:
        print(article.ressort, file=article_file)
        print("", file=article_file)
        print(article.title, file=article_file)
        print("", file=article_file)
        print(article.content, file=article_file)


@dataclass
class StorageOptions:
    """Options for how to store/serialize articles (e.g. which to ignore, how to
    construct the filename, ...)."""

    resorts_to_store_order: list[str] = field(
        default_factory=lambda: [
            "Politik",
            "Wissen",
            "Doktor",
            "Seite 1",
            "Recht und Unrecht",
            "Verbrechen",
            "Wirtschaft",
            "Streit",
            "Dossier",
            "Geschichte",
            "Chancen",
            "geld-spezial",
            "Kinder und Jugendbuch",
            "Leserbriefe",
            "Glauben und Zweifeln",
            "ZEIT magazin",
            "Kultursommer",
            "Musik-Spezial",
            "Literatur-Spezial",
            "Zeit zum Entdecken",
            "ZEIT der Leser",
            "Olympia",
        ]
    )
    ressort_blacklist: set[str] = field(
        default_factory=lambda: {
            "Golfen",
            "Hamburg",
            "Schweiz",
            "Oesterreich",
            "Österreich",
            "ZEIT im Osten",
            "Kinderzeit",
            "Fussball",
            "Fußball",
            "Feuilleton",
            "Leo - ZEIT fuer Kinder",
            "Stellenmarkt",
        }
    )
    filename_pattern: str = "{resort_index:03d}_{resort_name}_{article_title}.txt"


def load_options_from_config_file(
    path_to_config_file: pathlib.Path = DEFAULT_CONFIG_FILE_PATH,
) -> StorageOptions:
    """Load ``StorageOptions`` from a file following configparser syntax."""
    parser = configparser.ConfigParser()
    if isinstance(path_to_config_file, str):
        path_to_config_file = pathlib.Path(path_to_config_file)
    path_to_config_file = path_to_config_file.expanduser()
    print(f"Reading configuration from '{path_to_config_file}'.")
    parser.read(path_to_config_file)
    storage_options = parser["storage options"]
    options = StorageOptions(
        resorts_to_store_order=storage_options.get("resorts_to_store_order").split("\n"),
        ressort_blacklist=set(storage_options.get("ressort_blacklist").split("\n")),
        filename_pattern=storage_options.get("filename_pattern"),
    )
    return options


def _is_ressort_contained(ressort: str, ressorts: Iterable[str]) -> bool:
    return _index_of_ressort(ressort, ressorts) is not None


def _index_of_ressort(ressort: str, ressorts: Iterable[str]) -> int | None:
    """
    Return the position of the given resort in an iterable of ressorts.
    The check is performed fuzzy to match e.g. ``POLITIK`` and ``Politik``.
    Return the matching index or ``None`` if unable to find a match.
    """

    def ignore_nonalpha(character: str) -> bool:
        return not character.isalpha()

    for index, possible_match in enumerate(ressorts):
        matcher = difflib.SequenceMatcher(ignore_nonalpha, ressort.lower(), possible_match.lower())
        is_match = matcher.ratio() > 0.8
        if is_match:
            return index

    return None


@dataclass(frozen=True)
class StoredArticle(Article):
    """
    An article that was written to disc with content and path.
    """

    path: pathlib.Path


def store_articles(
    articles: list[Article],
    output_directory: pathlib.Path,
    storage_options: StorageOptions,
) -> tuple[set[str], list[StoredArticle]]:
    """
    Store each article as a single text file as defined by ``storage_options``.
    :return: Resorts not mentioned in the options and files written.
    """
    unmatched_ressorts: set[str] = set()
    stored_articles: list[StoredArticle] = []
    for article in articles:
        if _is_ressort_contained(article.ressort, storage_options.ressort_blacklist):
            continue

        ressort_index = _index_of_ressort(article.ressort, storage_options.resorts_to_store_order)
        if ressort_index is None:
            ressort_index = len(storage_options.resorts_to_store_order)
            unmatched_ressorts.add(article.ressort)

        output_file_path = output_directory / storage_options.filename_pattern.format(
            resort_index=ressort_index + 1,
            resort_name=_make_string_file_name_compatible(article.ressort),
            article_title=_make_string_file_name_compatible(article.title),
        )

        if output_file_path.exists():
            print(f"Warning: {output_file_path} already exists.")

        write_article_to_file(article, output_file_path)
        stored_articles.append(StoredArticle(**asdict(article), path=output_file_path))

    return unmatched_ressorts, stored_articles


# Helper


def _find_ressort(article: BeautifulSoup) -> str:
    # typically it's the first <span class=link>
    span = article.find("span", {"class": "link"})
    assert span is not None, "Unable to extract Ressort tag"
    ressort_link_text = span.get_text()
    match = re.match(r"\[Übersicht (.+)\]", ressort_link_text)
    assert match is not None, f"Unexpected Ressort link text {ressort_link_text}"
    return match.group(1)


def _find_content_quickly(article: BeautifulSoup) -> str:
    content_html = article.find("div", {"class": "article_text"})
    return content_html.get_text(separator="\n\n")


def _find_content(article: BeautifulSoup) -> str:
    content = ""
    if (subtitle := article.find("h3", {"class": "subtitle"})) is not None:
        content += subtitle.get_text()
    content_html = article.find("div", {"class": "article_text"})
    # remove blockquotes as they repeat text that will come later
    for blockquote in content_html.select("blockquote"):
        blockquote.extract()
    for paragraph in content_html.find_all("p", {"class": "paragraph"}):
        content += "\n\n" + paragraph.get_text()
    return content


def _extract_epub(epub_file_path: pathlib.Path, directory_to_extract_to: pathlib.Path) -> list[pathlib.Path]:
    """
    Extract an epub file.
    :return: paths to the files containing the actual articles.
    """
    with zipfile.ZipFile(epub_file_path, "r") as epub_file:
        epub_file.extractall(directory_to_extract_to)
    return list(pathlib.Path(directory_to_extract_to / "OEBPS").glob("article_*.xhtml"))


def _make_string_file_name_compatible(string: str) -> str:
    string = re.sub(r"\s+", "-", string)
    string = re.sub(r"ä", "ae", string)
    string = re.sub(r"ö", "oe", string)
    string = re.sub(r"ü", "ue", string)
    string = re.sub(r"Ä", "Ae", string)
    string = re.sub(r"Ö", "Oe", string)
    string = re.sub(r"Ü", "Ue", string)
    string = re.sub(r"ß", "ss", string)
    string = re.sub(r"[^a-zA-Z0-9_-]", "", string)
    string = re.sub(r"--+", "-", string)
    string = string.strip("-")
    return string


# CLI


@dataclass
class ExtractionOptions:
    """Top level information for extraction of a single epub file."""

    epub_input_file: pathlib.Path
    output_directory: pathlib.Path
    config_file_path: pathlib.Path


def parse_arguments() -> ExtractionOptions:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "epub_input_file",
        type=pathlib.Path,
        metavar="input.epub",
        help="Path to the 'Die Zeit' EPUB file.",
    )
    parser.add_argument(
        "output_directory",
        type=pathlib.Path,
        help="Path to the directory in which to place the extracted plain text files.",
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        dest="config_file_path",
        default=DEFAULT_CONFIG_FILE_PATH,
        help="Path to the configuration file to use; set to None to use built-in defaults.",
    )
    args = parser.parse_args()
    return ExtractionOptions(
        epub_input_file=args.epub_input_file,
        output_directory=args.output_directory,
        config_file_path=args.config_file_path,
    )


def main():
    """CLI entrypoint."""
    options = parse_arguments()
    if not options.output_directory.exists():
        options.output_directory.mkdir()
    articles = extract_articles(options.epub_input_file)
    storage_options = load_options_from_config_file(options.config_file_path)
    unmentioned_ressorts, _ = store_articles(articles, options.output_directory, storage_options)
    for ressort in unmentioned_ressorts:
        print(f"Warning: Classify ressort {ressort} in configuration!")


if __name__ == "__main__":
    main()

# %%
