"""
Module that contains the command line app.
"""
import os
import argparse
import shutil
import glob
from google.cloud import storage
from google.cloud import texttospeech

gcp_project = "project-e8f5a204-d5ce-4c07-9c7"
bucket_name = "sophie-mega-pipeline"
text_paragraphs = "text_paragraphs"  # English source text
text_translated = "text_translated"  # translated text, one folder per language
output_audios = "output_audios"      # synthesized audio, one folder per language
group_name = "sophies" # This needs to be your Group name e.g: group-01, group-02, group-03, group-04, group-05, ...
source_language = "en"

# Language code -> (Text-to-Speech locale, voice name). Long audio synthesis requires
# an explicit voice name. To add a language, pick a voice from
# https://cloud.google.com/text-to-speech/docs/voices and add it to
# SUPPORTED_LANGUAGES in orchestrator/api.py too.
VOICES = {
    "en": ("en-US", "en-US-Standard-B"),
    "fr": ("fr-FR", "fr-FR-Standard-C"),
    "es": ("es-ES", "es-ES-Standard-E"),
    "de": ("de-DE", "de-DE-Standard-G"),
    "it": ("it-IT", "it-IT-Standard-E"),
    "ja": ("ja-JP", "ja-JP-Standard-A"),
}

# Instantiates a client
client = texttospeech.TextToSpeechLongAudioSynthesizeClient()


def check_language(language):
    if language not in VOICES:
        raise ValueError(f"Unsupported language '{language}', choose from {list(VOICES)}")


def text_dir(language):
    # English is synthesized straight from the generated paragraphs
    if language == source_language:
        return os.path.join(text_paragraphs, group_name)
    return os.path.join(text_translated, language, group_name)


def download(language):
    print("download", language)
    check_language(language)

    # Clear
    shutil.rmtree(text_dir(language), ignore_errors=True, onerror=None)
    os.makedirs(text_dir(language), exist_ok=True)

    storage_client = storage.Client(project=gcp_project)
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(match_glob=f"{text_dir(language)}/input-*.txt")
    for blob in blobs:
        blob.download_to_filename(blob.name)


def synthesis(language):
    print("synthesis", language)
    check_language(language)
    language_code, voice_name = VOICES[language]

    storage_client = storage.Client(project=gcp_project)
    bucket = storage_client.bucket(bucket_name)

    # Get the list of text file
    text_files = glob.glob(os.path.join(text_dir(language), "input-*.txt"))
    for text_file in text_files:
        uuid = os.path.basename(text_file).replace(".txt", "")

        # Long audio synthesis only outputs LINEAR16, i.e. WAV
        audio_blob_name = f"{output_audios}/{language}/{group_name}/{uuid}.wav"
        if bucket.blob(audio_blob_name).exists():
            continue

        with open(text_file) as f:
            input_text = f.read()

        # Set the text input to be synthesized
        input = texttospeech.SynthesisInput(text=input_text)
        # Build audio config / Select the type of audio file you want returned
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
        # voice config
        voice = texttospeech.VoiceSelectionParams(language_code=language_code, name=voice_name)

        parent = f"projects/{gcp_project}/locations/us-central1"
        output_gcs_uri = f"gs://{bucket_name}/{audio_blob_name}"

        request = texttospeech.SynthesizeLongAudioRequest(
            parent=parent,
            input=input,
            audio_config=audio_config,
            voice=voice,
            output_gcs_uri=output_gcs_uri,
        )

        operation = client.synthesize_long_audio(request=request)
        # Set a deadline for your LRO to finish. 300 seconds is reasonable, but can be adjusted depending on the length of the input.
        operation.result(timeout=300)
        print("Audio saved to", output_gcs_uri)


def main(args=None):
    print("Args:", args)

    if args.download:
        download(args.language)
    if args.synthesis:
        synthesis(args.language)


if __name__ == "__main__":
    # Generate the inputs arguments parser
    # if you type into the terminal 'python cli.py --help', it will provide the description
    parser = argparse.ArgumentParser(description="Synthesis audio from text in any supported language")

    parser.add_argument(
        "-l",
        "--language",
        default="fr",
        help=f"Language code, one of {list(VOICES)} (default: fr)",
    )

    parser.add_argument(
        "-d",
        "--download",
        action="store_true",
        help="Download the text for that language from GCS bucket",
    )

    parser.add_argument(
        "-s", "--synthesis", action="store_true", help="Synthesis audio"
    )

    args = parser.parse_args()

    main(args)
