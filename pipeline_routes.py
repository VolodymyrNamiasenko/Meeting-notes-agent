import importlib.util
import os
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Blueprint, jsonify, render_template, request

import meeting_pipeline as pipeline
from audio_transcription import transcribe_audio
from database import get_db


def create_blueprint(load_config):
    bp = Blueprint("pipeline", __name__)

    @bp.before_request
    def same_origin():
        origin = request.headers.get("Origin")
        if (
            request.method == "POST"
            and origin
            and origin.rstrip("/") != request.host_url.rstrip("/")
        ):
            raise pipeline.PipelineError(
                "Use this workflow from the local application.", 403
            )

    @bp.errorhandler(pipeline.PipelineError)
    def failure(exc):
        return jsonify({"error": str(exc)}), exc.status

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise pipeline.PipelineError("A JSON object is required.")
        return value

    @bp.get("/pipeline")
    def page():
        with closing(get_db()) as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT id,title,meeting_date FROM transcriptions ORDER BY id DESC LIMIT 100"
                )
            ]
        return render_template("pipeline.html", transcripts=rows)

    @bp.get("/api/pipeline/status")
    def status():
        return jsonify(
            {
                "audio_ready": bool(
                    os.getenv("WHISPER_MODEL_PATH")
                    and importlib.util.find_spec("faster_whisper")
                    and Path(os.environ["WHISPER_MODEL_PATH"]).is_dir()
                ),
                "claude_configured": bool(
                    os.getenv("ANTHROPIC_API_KEY")
                    or load_config().get("anthropic_api_key")
                ),
            }
        )

    @bp.post("/api/pipeline/import")
    def import_text():
        data = body()
        result = pipeline.store_transcript(
            data.get("title"), data.get("meeting_date"), data.get("content")
        )
        return jsonify(result), 200 if result["duplicate"] else 201

    @bp.post("/api/pipeline/transcribe")
    def transcribe():
        title, meeting_date = pipeline.metadata(
            request.form.get("title"), request.form.get("meeting_date")
        )
        uploaded = request.files.get("audio")
        suffix = Path(uploaded.filename or "").suffix.lower() if uploaded else ""
        if uploaded is None or suffix not in {
            ".wav",
            ".mp3",
            ".m4a",
            ".flac",
            ".ogg",
            ".webm",
        }:
            raise pipeline.PipelineError(
                "Upload a WAV, MP3, M4A, FLAC, OGG or WebM audio file."
            )
        with TemporaryDirectory(prefix="meeting-audio-") as directory:
            path = Path(directory) / ("recording" + suffix)
            digest = sha256()
            count = 0
            with path.open("wb") as stream:
                while chunk := uploaded.stream.read(65536):
                    count += len(chunk)
                    if count > 18 * 1024 * 1024:
                        raise pipeline.PipelineError(
                            "Audio files must be at most 18 MB.", 413
                        )
                    digest.update(chunk)
                    stream.write(chunk)
            if not count:
                raise pipeline.PipelineError("The audio file is empty.")
            result = transcribe_audio(path)
            saved = pipeline.store_transcript(
                title,
                meeting_date,
                result["content"],
                "audio",
                source_hash=digest.hexdigest(),
                language=result["language"],
                segments=result["segments"],
            )
        return jsonify(
            {**saved, "duration_seconds": result["duration_seconds"]}
        ), 200 if saved["duplicate"] else 201

    @bp.post("/api/pipeline/transcripts/<int:identifier>/generate")
    def generate(identifier):
        data = body()
        if data.get("allow_external") is not True:
            raise pipeline.PipelineError(
                "Confirm that this transcript may be sent to Claude before generating a draft."
            )
        source = pipeline.transcript(identifier)
        notes = pipeline.generate_notes(source["content"], load_config())
        return jsonify(pipeline.save_draft(identifier, notes, "claude")), 201

    @bp.post("/api/pipeline/transcripts/<int:identifier>/draft")
    def manual_draft(identifier):
        return jsonify(
            pipeline.save_draft(identifier, body().get("notes"), "manual")
        ), 201

    @bp.get("/api/pipeline/drafts")
    def drafts():
        with closing(get_db()) as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT d.id,d.status,d.version,t.title FROM meeting_drafts d JOIN transcriptions t ON t.id=d.transcription_id ORDER BY d.id DESC LIMIT 100"
                )
            ]
        return jsonify({"items": rows})

    @bp.get("/api/pipeline/drafts/<int:identifier>")
    def draft(identifier):
        return jsonify(pipeline.draft(identifier))

    @bp.post("/api/pipeline/drafts/<int:identifier>/edit")
    def edit(identifier):
        data = body()
        return jsonify(
            pipeline.update_draft(
                identifier,
                data.get("version"),
                data.get("reviewer"),
                notes=data.get("notes"),
            )
        )

    @bp.post("/api/pipeline/drafts/<int:identifier>/review")
    def review(identifier):
        data = body()
        return jsonify(
            pipeline.update_draft(
                identifier,
                data.get("version"),
                data.get("reviewer"),
                data.get("note", ""),
                decision=data.get("decision"),
            )
        )

    return bp
