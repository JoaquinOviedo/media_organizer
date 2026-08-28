import os
import secrets
import time
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    request,
    send_file,
    send_from_directory,
    session,
    stream_with_context,
)

from src.google_photos_picker import GooglePhotosError, GooglePhotosPickerClient
from src.local_media import LocalMediaLibrary, choose_folder
from src.mvp_store import MvpStore
from src.token_vault import PersistentTokenVault, TokenVaultError


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

store = MvpStore(ROOT / "mvp.sqlite3")
local_library = LocalMediaLibrary(store)
google = GooglePhotosPickerClient(
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    redirect_uri=os.getenv(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8765/auth/google/callback"
    ),
)

token_vault = PersistentTokenVault()
extension_runtime = {"last_seen": 0.0, "version": None}


def _token() -> dict | None:
    return token_vault.get()


def _access_token() -> str:
    token = _token()
    if not token or not token.get("access_token"):
        raise GooglePhotosError("Primero conecta tu cuenta de Google.")

    expires_at = int(token.get("expires_at") or 0)
    if expires_at <= int(time.time()) + 90:
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise GooglePhotosError("La sesion de Google vencio. Volve a conectarla una vez.")
        refreshed = google.refresh_access_token(refresh_token)
        refreshed["user"] = token.get("user") or {}
        token_vault.save(refreshed)
        token = refreshed
    return token["access_token"]


@app.after_request
def allow_extension(response):
    origin = request.headers.get("Origin", "")
    if origin.startswith("chrome-extension://") or origin == "https://photos.google.com":
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.errorhandler(GooglePhotosError)
def google_error(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(TokenVaultError)
def token_vault_error(error):
    return jsonify({"error": str(error)}), 500


@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")


@app.get("/assets/<path:name>")
def assets(name: str):
    return send_from_directory(ROOT / "web", name)


@app.get("/api/status")
def status():
    token = _token()
    return jsonify(
        {
            "configured": google.configured,
            "connected": bool(token),
            "user": token.get("user") if token else None,
            "albumName": "Fotos a eliminar",
            "extensionActive": time.time() - extension_runtime["last_seen"] < 75,
            "extensionVersion": extension_runtime["version"],
            "extensionPath": str(ROOT / "extension"),
        }
    )


@app.get("/api/local/status")
def local_status():
    return jsonify(local_library.status())


@app.post("/api/local/folder/select")
def select_local_folder():
    try:
        selected = choose_folder()
    except Exception as error:
        return jsonify({"error": f"No se pudo abrir el selector de carpetas: {error}"}), 500
    if not selected:
        return jsonify({"cancelled": True})
    try:
        return jsonify(local_library.scan(selected))
    except (OSError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/local/folder/rescan")
def rescan_local_folder():
    library = store.get_local_library()
    if not library:
        return jsonify({"error": "Primero elegí una carpeta."}), 400
    try:
        return jsonify(local_library.scan(library["root_path"]))
    except (OSError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.get("/api/local/media")
def local_media_items():
    return jsonify({"items": local_library.list_items()})


@app.get("/api/local/media/<item_id>/content")
def local_media_content(item_id: str):
    item = local_library.get_item(item_id)
    if not item:
        return jsonify({"error": "Archivo no encontrado."}), 404
    try:
        path = local_library.content_path(item_id)
    except (FileNotFoundError, OSError) as error:
        return jsonify({"error": str(error)}), 404

    if item["type"] == "IMAGE" and path.suffix.lower() in {".heic", ".heif", ".tif", ".tiff"}:
        try:
            from PIL import Image
            import pillow_heif

            pillow_heif.register_heif_opener()
            with Image.open(path) as image:
                image.thumbnail((2200, 2200))
                converted = BytesIO()
                image.convert("RGB").save(converted, "JPEG", quality=90)
            converted.seek(0)
            response = send_file(converted, mimetype="image/jpeg", download_name=f"{path.stem}.jpg")
        except Exception as error:
            return jsonify({"error": f"No se pudo previsualizar esta imagen: {error}"}), 415
    else:
        response = send_file(
            path,
            mimetype=item.get("mime_type"),
            conditional=True,
            etag=True,
            last_modified=path.stat().st_mtime,
        )
    response.headers["Cache-Control"] = "private, max-age=60"
    return response


@app.post("/api/local/media/<item_id>/decision")
def local_media_decision(item_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        item = local_library.decide(item_id, payload.get("decision", ""))
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except (OSError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ok": True, "item": item, "status": local_library.status()})


@app.post("/api/local/later/reset")
def reset_local_later():
    count = store.reset_local_later()
    return jsonify({"ok": True, "resetCount": count, "status": local_library.status()})


@app.get("/auth/google")
def auth_google():
    attempt = google.create_authorization_attempt()
    session["oauth_state"] = attempt.state
    session["oauth_verifier"] = attempt.verifier
    return redirect(attempt.authorization_url)


@app.get("/auth/google/callback")
def auth_google_callback():
    if request.args.get("error"):
        return redirect("/?auth=cancelled")
    state = request.args.get("state", "")
    if not state or not secrets.compare_digest(state, session.pop("oauth_state", "")):
        raise GooglePhotosError("La validacion de seguridad de OAuth no coincide.")
    verifier = session.pop("oauth_verifier", "")
    token = google.exchange_code(request.args.get("code", ""), verifier)
    previous = _token()
    if previous and not token.get("refresh_token"):
        token["refresh_token"] = previous.get("refresh_token")
    token["user"] = google.user_info(token["access_token"])
    token_vault.save(token)
    return redirect("/?auth=connected")


@app.post("/api/disconnect")
def disconnect():
    token_vault.clear()
    return jsonify({"ok": True})


@app.post("/api/picker/sessions")
def create_picker_session():
    payload = request.get_json(silent=True) or {}
    requested = int(payload.get("maxItemCount", 200))
    max_items = max(1, min(requested, 2000))
    picker_session = google.create_picker_session(_access_token(), max_items)
    return jsonify(picker_session)


@app.get("/api/picker/sessions/<session_id>")
def picker_session_status(session_id: str):
    picker_session = google.get_picker_session(_access_token(), session_id)
    if picker_session.get("mediaItemsSet"):
        items = google.list_media_items(_access_token(), session_id)
        store.upsert_picker_items(session_id, items)
        picker_session["importedCount"] = len(items)
    return jsonify(picker_session)


@app.get("/api/media")
def media_items():
    decision = request.args.get("decision")
    if decision and decision not in {"pending", "keep", "delete", "later"}:
        return jsonify({"error": "Filtro de decision invalido."}), 400
    items = store.list_media()
    if decision:
        items = [item for item in items if item.get("decision") == decision]
    return jsonify({"items": items})


@app.get("/api/media/<path:item_id>/preview")
def media_preview(item_id: str):
    item = store.get_media(item_id)
    if not item or not item.get("base_url"):
        return jsonify({"error": "Foto no encontrada."}), 404
    preview = google.download_preview(_access_token(), item["base_url"], item["type"])
    response = app.response_class(
        preview.content,
        status=200,
        content_type=preview.headers.get("Content-Type", item.get("mime_type")),
    )
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@app.get("/api/media/<path:item_id>/video")
def media_video(item_id: str):
    item = store.get_media(item_id)
    if not item or not item.get("base_url"):
        return jsonify({"error": "Video no encontrado."}), 404
    if item.get("type") != "VIDEO" and not str(item.get("mime_type", "")).startswith("video/"):
        return jsonify({"error": "El elemento solicitado no es un video."}), 400

    remote = google.stream_video(
        _access_token(),
        item["base_url"],
        request.headers.get("Range"),
    )

    def chunks():
        try:
            yield from remote.iter_content(chunk_size=256 * 1024)
        finally:
            remote.close()

    response = app.response_class(
        stream_with_context(chunks()),
        status=remote.status_code,
        content_type=remote.headers.get("Content-Type", item.get("mime_type") or "video/mp4"),
        direct_passthrough=True,
    )
    for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
        if remote.headers.get(header):
            response.headers[header] = remote.headers[header]
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@app.post("/api/media/<path:item_id>/decision")
def media_decision(item_id: str):
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in {"pending", "keep", "delete", "later"}:
        return jsonify({"error": "Decision invalida."}), 400
    if not store.set_media_decision(item_id, decision):
        return jsonify({"error": "Foto no encontrada."}), 404
    return jsonify({"ok": True, "decision": decision})


@app.route("/api/extension/decisions", methods=["GET", "POST", "OPTIONS"])
def extension_decisions():
    if request.method == "OPTIONS":
        return "", 204
    if request.method == "GET":
        return jsonify({"items": store.list_extension_decisions()})
    payload = request.get_json(silent=True) or {}
    required = ("photoId", "photoUrl", "decision", "albumStatus")
    if any(not payload.get(field) for field in required):
        return jsonify({"error": "Faltan datos de la decision."}), 400
    store.record_extension_decision(
        photo_id=payload["photoId"],
        photo_url=payload["photoUrl"],
        decision=payload["decision"],
        album_status=payload["albumStatus"],
        message=payload.get("message"),
    )
    return jsonify({"ok": True})


@app.route("/api/extension/heartbeat", methods=["POST", "OPTIONS"])
def extension_heartbeat():
    if request.method == "OPTIONS":
        return "", 204
    payload = request.get_json(silent=True) or {}
    extension_runtime["last_seen"] = time.time()
    extension_runtime["version"] = str(payload.get("version") or "local")[:32]
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.getenv("MVP_HOST", "127.0.0.1")
    port = int(os.getenv("MVP_PORT", "8765"))
    app.run(host=host, port=port, debug=False)
