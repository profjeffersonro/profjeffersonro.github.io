#!/usr/bin/env python3
"""
Publica uma aula no portal:

1. Copia o HTML gerado para o caminho correspondente em content/.
2. Copia assets locais referenciados pelo HTML.
3. Envia ou atualiza o PDF no Google Drive.
4. Atualiza o link do PDF no config.yaml.
5. Executa build.py.
6. Opcionalmente faz commit e push.

O script usa apenas biblioteca padrao do Python para o Drive, reaproveitando:
  /home/jefferson/Documentos/Gdrive/config/sync_config.json
  /home/jefferson/Documentos/Gdrive/config/client_secret.json
  /home/jefferson/Documentos/Gdrive/config/token.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRIVE_CONFIG = Path("/home/jefferson/Documentos/Gdrive/config")


class PublishError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[publish] {message}")


def run(cmd: list[str], *, cwd: Path = REPO_ROOT, dry_run: bool = False) -> subprocess.CompletedProcess[str] | None:
    log("$ " + " ".join(cmd))
    if dry_run:
        return None
    return subprocess.run(cmd, cwd=cwd, text=True, check=True)


def rel_to_repo(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def assert_in_repo(path: Path) -> None:
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError as exc:
        raise PublishError(f"Caminho fora do repositorio: {path}") from exc


def quote_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublishError(f"Arquivo nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PublishError(f"JSON invalido: {path}: {exc}") from exc


def parse_drive_time(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        value = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


@dataclass
class DriveClient:
    config_dir: Path
    sync_config: dict
    token: dict
    token_path: Path

    @classmethod
    def from_config_dir(cls, config_dir: Path) -> "DriveClient":
        sync_config = load_json(config_dir / "sync_config.json")
        token_name = sync_config.get("token_file") or "token.json"
        token_path = config_dir / token_name
        return cls(config_dir=config_dir, sync_config=sync_config, token=load_json(token_path), token_path=token_path)

    @property
    def access_token(self) -> str:
        self.ensure_token()
        token = self.token.get("token")
        if not token:
            raise PublishError("token.json nao contem access token.")
        return token

    @property
    def root_folder_id(self) -> str:
        folder_id = self.sync_config.get("drive_folder_id")
        if not folder_id:
            raise PublishError("sync_config.json nao contem drive_folder_id.")
        return folder_id

    @property
    def local_root(self) -> Path | None:
        local_folder = self.sync_config.get("local_folder")
        return Path(local_folder).expanduser() if local_folder else None

    @property
    def make_public(self) -> bool:
        return bool(self.sync_config.get("make_public", True))

    def ensure_token(self) -> None:
        expires_at = parse_drive_time(self.token.get("expiry"))
        if expires_at and expires_at - time.time() > 120:
            return
        self.refresh_token()

    def refresh_token(self) -> None:
        client_id = self.token.get("client_id")
        client_secret = self.token.get("client_secret")
        refresh_token = self.token.get("refresh_token")
        if not client_id or not client_secret:
            secret = load_json(self.config_dir / (self.sync_config.get("credentials_file") or "client_secret.json"))
            installed = secret.get("installed", {})
            client_id = client_id or installed.get("client_id")
            client_secret = client_secret or installed.get("client_secret")
        if not client_id or not client_secret or not refresh_token:
            raise PublishError("Nao foi possivel renovar token do Drive: client_id/client_secret/refresh_token ausentes.")

        body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        data = self._open_json(req, authenticated=False)
        self.token["token"] = data["access_token"]
        if "expires_in" in data:
            expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(data["expires_in"]))
            self.token["expiry"] = expiry.isoformat().replace("+00:00", "Z")
        self.token_path.write_text(json.dumps(self.token, indent=2, ensure_ascii=False), encoding="utf-8")
        log("Token do Drive renovado.")

    def request_json(self, method: str, url: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=UTF-8"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        return self._open_json(req)

    def _open_json(self, req: urllib.request.Request, *, authenticated: bool = True) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PublishError(f"Erro HTTP no Drive ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            suffix = " autenticada" if authenticated else ""
            raise PublishError(f"Falha de rede na requisicao{suffix} ao Drive: {exc}") from exc

    def find_file(self, name: str, parent_id: str, mime_type: str | None = None) -> dict | None:
        parts = [
            f"name = '{quote_drive_query(name)}'",
            f"'{quote_drive_query(parent_id)}' in parents",
            "trashed = false",
        ]
        if mime_type:
            parts.append(f"mimeType = '{quote_drive_query(mime_type)}'")
        query = " and ".join(parts)
        params = urllib.parse.urlencode({"q": query, "fields": "files(id,name,mimeType,webViewLink)", "pageSize": "10"})
        data = self.request_json("GET", f"https://www.googleapis.com/drive/v3/files?{params}")
        files = data.get("files", [])
        return files[0] if files else None

    def ensure_folder(self, name: str, parent_id: str, dry_run: bool = False) -> str:
        if dry_run:
            log(f"[dry-run] Criaria/validaria pasta no Drive: {name}")
            return parent_id
        mime = "application/vnd.google-apps.folder"
        found = self.find_file(name, parent_id, mime)
        if found:
            return found["id"]
        log(f"Criando pasta no Drive: {name}")
        created = self.request_json(
            "POST",
            "https://www.googleapis.com/drive/v3/files?fields=id",
            {"name": name, "mimeType": mime, "parents": [parent_id]},
        )
        return created["id"]

    def ensure_folder_path(self, parts: list[str], dry_run: bool = False) -> str:
        parent_id = self.root_folder_id
        for part in parts:
            if part:
                parent_id = self.ensure_folder(part, parent_id, dry_run=dry_run)
        return parent_id

    def upload_pdf(self, pdf_path: Path, parent_id: str, dry_run: bool = False) -> str:
        if dry_run:
            return "https://drive.google.com/file/d/DRY_RUN_FILE_ID/view?usp=drive_link"
        existing = self.find_file(pdf_path.name, parent_id)

        metadata = {"name": pdf_path.name}
        if not existing:
            metadata["parents"] = [parent_id]

        file_id = existing["id"] if existing else None
        url = "https://www.googleapis.com/upload/drive/v3/files"
        method = "POST"
        if file_id:
            url += f"/{file_id}"
            method = "PATCH"
        url += "?uploadType=multipart&fields=id,webViewLink"

        boundary = "===============%s==" % uuid.uuid4().hex
        content_type = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"
        pdf_bytes = pdf_path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
                json.dumps(metadata).encode("utf-8"),
                b"\r\n",
                f"--{boundary}\r\n".encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                pdf_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            method=method,
        )
        result = self._open_json(req)
        file_id = result["id"]
        if self.make_public:
            self.make_file_public(file_id)
        return result.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"

    def make_file_public(self, file_id: str) -> None:
        try:
            self.request_json(
                "POST",
                f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                {"role": "reader", "type": "anyone"},
            )
        except PublishError as exc:
            message = str(exc)
            if "alreadyExists" not in message and "duplicate" not in message:
                raise


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value for key, value in attrs if value}
        for attr in ("src", "href", "poster"):
            value = attrs_dict.get(attr)
            if value:
                self.refs.add(value)
        srcset = attrs_dict.get("srcset")
        if srcset:
            for item in srcset.split(","):
                candidate = item.strip().split(" ")[0]
                if candidate:
                    self.refs.add(candidate)


def is_local_ref(ref: str) -> bool:
    if ref.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
        return False
    parsed = urllib.parse.urlparse(ref)
    return not parsed.scheme and not parsed.netloc


def referenced_local_assets(html_path: Path) -> list[tuple[Path, str]]:
    parser = AssetParser()
    parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    assets: list[tuple[Path, str]] = []
    for ref in sorted(parser.refs):
        if not is_local_ref(ref):
            continue
        parsed = urllib.parse.urlparse(ref)
        rel = urllib.parse.unquote(parsed.path)
        if not rel or rel.endswith(".html"):
            continue
        source = (html_path.parent / rel).resolve()
        if source.is_file():
            assets.append((source, rel))
    return assets


def copy_html_and_assets(source_html: Path, dest_html: Path, dry_run: bool = False) -> list[Path]:
    touched = [dest_html]
    assert_in_repo(dest_html)
    log(f"Copiando HTML: {source_html} -> {dest_html}")
    if not dry_run:
        dest_html.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_html, dest_html)

    for source, rel in referenced_local_assets(source_html):
        dest = (dest_html.parent / rel).resolve()
        assert_in_repo(dest)
        touched.append(dest)
        log(f"Copiando asset: {source} -> {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    return touched


def find_config_entry(config_path: Path, source_html: Path, explicit_html: str | None) -> str:
    text = config_path.read_text(encoding="utf-8")
    html_values = re.findall(r"^\s*html:\s*['\"]?([^'\"\n]+)['\"]?\s*$", text, flags=re.MULTILINE)
    if explicit_html:
        if explicit_html not in html_values:
            raise PublishError(f"--content-html nao encontrado no config.yaml: {explicit_html}")
        return explicit_html

    matches = [value for value in html_values if Path(value).name == source_html.name]
    if not matches:
        raise PublishError(
            "Nao encontrei entrada no config.yaml para esse HTML. "
            "Use --content-html content/aulas/.../arquivo.html."
        )
    if len(matches) > 1:
        formatted = "\n  - ".join(matches)
        raise PublishError(f"Mais de uma entrada usa esse nome de HTML. Use --content-html.\n  - {formatted}")
    return matches[0]


def update_yaml_pdf(config_path: Path, html_value: str, pdf_url: str, dry_run: bool = False) -> bool:
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    html_re = re.compile(r"^(\s*)html:\s*(['\"]?)([^'\"\n]+)(['\"]?)\s*$")
    pdf_re = re.compile(r"^(\s*)pdf:\s*.*$")

    html_idx = None
    html_indent = ""
    for idx, line in enumerate(lines):
        match = html_re.match(line.rstrip("\n"))
        if match and match.group(3) == html_value:
            html_idx = idx
            html_indent = match.group(1)
            break
    if html_idx is None:
        raise PublishError(f"Entrada html nao encontrada no YAML: {html_value}")

    replacement = f'{html_indent}pdf: "{pdf_url}"\n'
    insert_at = html_idx + 1
    for idx in range(html_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("- name:") or stripped.startswith("- title:") or stripped.startswith("- disciplina:"):
            break
        if pdf_re.match(lines[idx].rstrip("\n")):
            if lines[idx] == replacement:
                log("config.yaml ja continha o link atual do PDF.")
                return False
            log(f"Atualizando link PDF em config.yaml para {html_value}")
            if not dry_run:
                lines[idx] = replacement
                config_path.write_text("".join(lines), encoding="utf-8")
            return True
        insert_at = idx + 1

    log(f"Inserindo link PDF em config.yaml para {html_value}")
    if not dry_run:
        lines.insert(insert_at, replacement)
        config_path.write_text("".join(lines), encoding="utf-8")
    return True


def drive_folder_parts(client: DriveClient, source_pdf: Path) -> list[str]:
    local_root = client.local_root
    if not local_root:
        return []
    try:
        relative_parent = source_pdf.parent.resolve().relative_to(local_root.resolve())
    except ValueError:
        return []
    return list(relative_parent.parts)


def git_dirty_paths() -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths: set[str] = set()
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        paths.add(entry[3:].split(" -> ")[-1])
    return paths


def resolve_source_file(lesson_dir: Path, value: str | None, suffix: str) -> Path:
    if value:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = lesson_dir / path
        return path.resolve()
    matches = sorted(lesson_dir.glob(f"*{suffix}"))
    matches = [
        path
        for path in matches
        if not path.name.endswith(f"-auto{suffix}")
        and not path.name.startswith("resp-")
        and ".backup." not in path.name
    ]
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise PublishError(f"Nenhum arquivo {suffix} encontrado em {lesson_dir}.")
    raise PublishError(f"Mais de um arquivo {suffix} encontrado. Informe --{suffix.lstrip('.')}.")


def resolve_source_html(lesson_dir: Path, value: str | None, source_pdf: Path) -> Path:
    if value:
        return resolve_source_file(lesson_dir, value, ".html")

    same_stem = lesson_dir / f"{source_pdf.stem}.html"
    if same_stem.is_file():
        return same_stem.resolve()

    matches = sorted(lesson_dir.glob("*.html"))
    matches = [
        path
        for path in matches
        if not path.name.endswith("-auto.html")
        and not path.name.startswith("resp-")
        and ".backup." not in path.name
    ]
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise PublishError(f"Nenhum arquivo .html principal encontrado em {lesson_dir}.")
    raise PublishError("Mais de um HTML principal encontrado. Informe --html.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publica HTML/PDF de aula no portal e no Google Drive.")
    parser.add_argument("--lesson-dir", default=".", help="Pasta da aula gerada pelo make.sh.")
    parser.add_argument("--html", help="HTML gerado. Padrao: unico *.html da pasta, exceto *-auto.html.")
    parser.add_argument("--pdf", help="PDF gerado. Padrao: unico *.pdf da pasta.")
    parser.add_argument("--content-html", help="Caminho content/... correspondente no config.yaml.")
    parser.add_argument("--config", default="config.yaml", help="Arquivo YAML do portal.")
    parser.add_argument("--drive-config", default=str(DEFAULT_DRIVE_CONFIG), help="Pasta com sync_config.json/token.json.")
    parser.add_argument("--skip-drive", action="store_true", help="Nao envia PDF; apenas copia HTML/assets e builda.")
    parser.add_argument("--skip-build", action="store_true", help="Nao executa build.py.")
    parser.add_argument("--build-mode", choices=["full", "incremental"], default="full")
    parser.add_argument("--commit", action="store_true", help="Faz commit dos arquivos tocados.")
    parser.add_argument("--push", action="store_true", help="Faz push apos o commit. Implica --commit.")
    parser.add_argument("--allow-dirty", action="store_true", help="Permite commit mesmo com alteracoes previas no repositorio.")
    parser.add_argument("--message", help="Mensagem de commit.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que faria, sem alterar arquivos nem chamar git.")
    args = parser.parse_args(argv)

    lesson_dir = Path(args.lesson_dir).expanduser().resolve()
    source_pdf = resolve_source_file(lesson_dir, args.pdf, ".pdf")
    source_html = resolve_source_html(lesson_dir, args.html, source_pdf)
    config_path = (REPO_ROOT / args.config).resolve()
    assert_in_repo(config_path)

    if not source_html.is_file():
        raise PublishError(f"HTML nao encontrado: {source_html}")
    if not source_pdf.is_file():
        raise PublishError(f"PDF nao encontrado: {source_pdf}")

    dirty_before = git_dirty_paths()
    if (args.commit or args.push) and dirty_before and not args.allow_dirty:
        raise PublishError(
            "Repositorio ja possui alteracoes pendentes. "
            "Revise com git status ou use --allow-dirty para commitar apenas os arquivos tocados pelo script."
        )

    html_value = find_config_entry(config_path, source_html, args.content_html)
    dest_html = (REPO_ROOT / html_value).resolve()
    touched = copy_html_and_assets(source_html, dest_html, dry_run=args.dry_run)

    pdf_url = None
    if not args.skip_drive:
        client = DriveClient.from_config_dir(Path(args.drive_config).expanduser())
        folder_id = client.ensure_folder_path(drive_folder_parts(client, source_pdf), dry_run=args.dry_run)
        log(f"Enviando PDF para o Drive: {source_pdf.name}")
        pdf_url = client.upload_pdf(source_pdf, folder_id, dry_run=args.dry_run)
        log(f"Link do PDF: {pdf_url}")
        if update_yaml_pdf(config_path, html_value, pdf_url, dry_run=args.dry_run):
            touched.append(config_path)

    if not args.skip_build:
        build_arg = "--full" if args.build_mode == "full" else "--incremental"
        run(["python3", "build.py", build_arg], dry_run=args.dry_run)

    if args.commit or args.push:
        dirty_after = git_dirty_paths()
        new_dirty_paths = dirty_after - dirty_before
        explicit_paths = {rel_to_repo(path) for path in touched if path.exists()}
        unique_paths = sorted(explicit_paths | new_dirty_paths)
        if not unique_paths:
            raise PublishError("Nenhum arquivo para stage/commit.")
        run(["git", "add", "--", *unique_paths], dry_run=args.dry_run)
        message = args.message or f"Publica aula: {source_html.stem}"
        run(["git", "commit", "-m", message], dry_run=args.dry_run)
    if args.push:
        run(["git", "push"], dry_run=args.dry_run)

    log("Fluxo concluido.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
