"""
Module that contains the command line app.
"""
import os
import argparse
import shutil
import glob
from google.cloud import storage
from google.cloud import translate_v2 as translate

# Generate the inputs arguments parser
parser = argparse.ArgumentParser(description="Command description.")

gcp_project = "project-e8f5a204-d5ce-4c07-9c7"
bucket_name = "sophie-mega-pipeline"
text_paragraphs = "text_paragraphs"
text_translated = "text_translated"
source_language = "en"
group_name = "sophies" # This needs to be your Group name e.g: group-01, group-02, group-03, group-04, group-05, ...

translate_client = translate.Client()


def translated_dir(language):
    return os.path.join(text_translated, language, group_name)


def makedirs(language=None):
    os.makedirs(os.path.join(text_paragraphs,group_name), exist_ok=True)
    if language:
        os.makedirs(translated_dir(language), exist_ok=True)


def download():
    print("download")

    # Clear
    shutil.rmtree(text_paragraphs, ignore_errors=True, onerror=None)
    makedirs()

    storage_client = storage.Client(project=gcp_project)
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(match_glob=f"{text_paragraphs}/{group_name}/input-*.txt")
    for blob in blobs:
        blob.download_to_filename(blob.name)


def translate(language):
    print("translate", language)
    if language == source_language:
        raise ValueError(f"Text is already in {source_language}, nothing to translate")
    makedirs(language)

    # Get the list of text file
    text_files = glob.glob(os.path.join(text_paragraphs, group_name, "input-*.txt"))
    for text_file in text_files:
        uuid = os.path.basename(text_file).replace(".txt", "")
        translated_file = os.path.join(translated_dir(language), uuid + ".txt")

        if os.path.exists(translated_file):
            continue

        with open(text_file) as f:
            input_text = f.read()

        result = translate_client.translate(
            input_text,
            source_language=source_language,
            target_language=language,
            format_="text",
        )
        translated_text = result["translatedText"]
        print(translated_text)

        # Save the translation
        with open(translated_file, "w") as f:
            f.write(translated_text)


def upload(language):
    print("upload", language)
    makedirs(language)

    # Upload to bucket
    storage_client = storage.Client(project=gcp_project)
    bucket = storage_client.bucket(bucket_name)

    # Get the list of text file
    text_files = glob.glob(os.path.join(translated_dir(language), "input-*.txt"))

    for text_file in text_files:
        filename = os.path.basename(text_file)
        destination_blob_name = os.path.join(translated_dir(language), filename)
        blob = bucket.blob(destination_blob_name)
        print("Uploading:",destination_blob_name, text_file)
        blob.upload_from_filename(text_file)


def main(args=None):
    print("Args:", args)

    if args.download:
        download()
    if args.translate:
        translate(args.language)
    if args.upload:
        upload(args.language)


if __name__ == "__main__":
    # Generate the inputs arguments parser
    # if you type into the terminal 'python cli.py --help', it will provide the description
    parser = argparse.ArgumentParser(description="Translate English text to another language")

    parser.add_argument(
        "-d",
        "--download",
        action="store_true",
        help="Download text paragraphs from GCS bucket",
    )

    parser.add_argument(
        "-l",
        "--language",
        default="fr",
        help="Target language code, e.g. fr, es, de, ja (default: fr)",
    )

    parser.add_argument("-t", "--translate", action="store_true", help="Translate text")

    parser.add_argument(
        "-u",
        "--upload",
        action="store_true",
        help="Upload translated text to GCS bucket",
    )

    args = parser.parse_args()

    main(args)
