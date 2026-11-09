# Audio, notes and review workflow

## Text and Notion

Start the app using the README. Open **Import and review**, enter a title/date and paste a transcript. Existing Notion sync also makes imported transcripts available in the selector. Text imports deduplicate by content/title/date. The local database retains transcripts and drafts; use `MEETING_DB_PATH` for an isolated demonstration and never commit it.

To generate notes, configure an Anthropic key privately in Settings or `ANTHROPIC_API_KEY`, and optionally `ANTHROPIC_MODEL`. Check the consent box and explicitly click **Generate draft with Claude**. This may incur provider charges and sends the selected transcript off-machine. No remote generation is triggered just by importing a transcript. Generation is limited to 80,000 transcript characters; longer transcripts must be split. The API key is never stored in a draft or returned by the workflow status route.

Every decision, action and topic must include an exact quote from the transcript. Unknown owners must be empty. Empty item lists are valid. Quote validation does not prove that a paraphrase is accurate; compare it with the source. The JSON schema is shown in `meeting_pipeline.SCHEMA_EXAMPLE`.

Edit and save a draft, then approve or reject it with a reviewer name. Approval atomically creates a local meeting, decisions and **pending** ticket drafts. It does not send remote tasks. Repeated/stale approval returns a conflict and does not create duplicate meetings. The local audit history records generation, edits and the decision. Reviewer names are self-reported; this is not a multi-user approval/security system.

## Optional local speech-to-text

```bash
pip install -r requirements-audio.txt
```

Download a compatible CTranslate2 Whisper model yourself, for example:

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-tiny.en', local_dir='./local-models/tiny.en', allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])"
export WHISPER_MODEL_PATH=/absolute/path/to/local-models/tiny.en
python app.py
```

Use a model with the languages you need; `tiny.en` is English only. The application requires a local directory and uses `local_files_only=True`; normal uploads never trigger model downloads. CPU inference uses int8 and two threads. Recordings stay local during transcription. Temporary uploaded audio is deleted on success/failure; transcript text and segment timestamps persist in SQLite.

Upload WAV, MP3, M4A, FLAC, OGG or WebM, at most 18 MB and 20 minutes. Audio is decoded/resampled with PyAV while enforcing the duration bound, then transcribed. One recording is processed at a time; concurrent inference receives a retry response. Long recordings should be split. This is a synchronous local workflow, not a background transcription cluster. Configure the same body/time limits in any proxy; do not expose this single-user app publicly without a security design.

See [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper) for model and platform requirements, and [Anthropic Messages](https://platform.claude.com/docs/en/api/messages) for provider configuration. No direct Sembly SDK/API integration is claimed; Sembly remains an optional upstream export source.

## Evaluation

```bash
python -m unittest discover -s tests -v
python -m evaluation.run_checks
python -m unittest discover -s tests -p test_audio.py -v
```

The last command requires the audio extra. Tests cover actual audio decoding/resampling/duration limits without downloading a model; the inference adapter is mocked in CI. Core workflow tests use temporary databases and mocked remote services. They cover evidence rejection, consent, import deduplication, version conflicts and approval without automatic remote writes. Synthetic cases are development regressions, not a representative held-out benchmark.

An explicitly requested real audio smoke check can report word error rate against a reference:

```bash
python -m evaluation.run_checks --audio /path/to/invented.wav --reference /path/to/reference.txt
```

This prints numeric metadata/metrics, not transcript text. WER normalises case and punctuation and includes insertions/deletions/substitutions; values may exceed 1. A single audio smoke example is not a deployment-quality claim. Real Claude output quality, Notion permissions/API compatibility and live task destinations need separate acceptance checks using permitted data and accounts.
