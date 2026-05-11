#!/usr/bin/env python3
"""
Fluxo interativo para publicar varias aulas.

Este script conversa pelo terminal, mas reutiliza publish_lesson.py para as
operacoes criticas de copia, Drive, YAML e build.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import publish_lesson as publish  # noqa: E402


@dataclass
class LessonCandidate:
    lesson_dir: Path
    source_html: Path
    source_pdf: Path
    answers_pdf: Path | None
    html_value: str | None
    expected_html_value: str | None
    in_config: bool
    in_content: bool
    title: str
    warnings: list[str]


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "S/n" if default else "s/N"
    while True:
        value = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"s", "sim", "y", "yes"}:
            return True
        if value in {"n", "nao", "não", "no"}:
            return False
        print("Responda com s ou n.")


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print("$ " + " ".join(cmd), flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def git_status_short() -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def lesson_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)", path.name)
    number = int(match.group(1)) if match else 10**9
    return number, path.name.lower()


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def extract_lesson_title(html_path: Path, fallback: str) -> str:
    text = html_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r'<h2[^>]*class=["\'][^"\']*document-subtitle[^"\']*["\'][^>]*>(.*?)</h2>',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        title = " ".join(strip_tags(unescape(match.group(1))).split())
        if title:
            return title

    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        title = " ".join(strip_tags(unescape(match.group(1))).split())
        if title and title.lower() not in {"documento", "aula"}:
            return title

    return fallback.replace("-", " ")


def discover_lesson_dirs(base_path: Path) -> list[Path]:
    base_path = base_path.expanduser().resolve()
    if not base_path.exists():
        raise publish.PublishError(f"Pasta nao encontrada: {base_path}")
    if not base_path.is_dir():
        raise publish.PublishError(f"Caminho nao e pasta: {base_path}")

    try:
        publish.resolve_source_pdf(base_path, None, None)
        publish.resolve_source_html(base_path, None, publish.resolve_source_pdf(base_path, None, None))
        return [base_path]
    except publish.PublishError:
        pass

    candidates: list[Path] = []
    for child in sorted((p for p in base_path.iterdir() if p.is_dir()), key=lesson_sort_key):
        if not re.search(r"aula[- ]?\d+", child.name, flags=re.IGNORECASE):
            continue
        if list(child.glob("*.html")) and list(child.glob("*.pdf")):
            candidates.append(child)
    return candidates


def config_html_values(config_path: Path) -> list[str]:
    text = config_path.read_text(encoding="utf-8")
    return re.findall(r"^\s*html:\s*['\"]?([^'\"\n]+)['\"]?\s*$", text, flags=re.MULTILINE)


def config_lesson_name(config_path: Path, html_value: str) -> str | None:
    text = config_path.read_text(encoding="utf-8")
    pattern = (
        r"-\s+name:\s*['\"]([^'\"]+)['\"]"
        r"(?:(?!\n\s*-\s+name:|\n\s*-\s+disciplina:|\nblog:).)*?"
        rf"\n\s*html:\s*['\"]{re.escape(html_value)}['\"]"
    )
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1) if match else None


def resolve_lesson_files(lesson_dir: Path, config_path: Path) -> tuple[Path, Path, str | None]:
    try:
        source_pdf = publish.resolve_source_pdf(lesson_dir, None, None)
        source_html = publish.resolve_source_html(lesson_dir, None, source_pdf)
        html_value = publish.find_config_entry(config_path, source_html, None)
        return source_html, source_pdf, html_value
    except publish.PublishError:
        pass

    matching_html_values = []
    local_html_names = {path.name for path in lesson_dir.glob("*.html")}
    for html_value in config_html_values(config_path):
        if Path(html_value).name in local_html_names:
            matching_html_values.append(html_value)

    if len(matching_html_values) != 1:
        raise publish.PublishError("nao foi possivel escolher HTML principal automaticamente")

    html_value = matching_html_values[0]
    source_html = (lesson_dir / Path(html_value).name).resolve()
    source_pdf = (lesson_dir / f"{source_html.stem}.pdf").resolve()
    if not source_pdf.is_file():
        raise publish.PublishError(f"PDF com mesmo nome do HTML nao encontrado: {source_pdf.name}")
    return source_html, source_pdf, html_value


def find_answers_pdf(lesson_dir: Path) -> tuple[Path | None, str | None]:
    matches = sorted(
        path
        for path in lesson_dir.glob("resp-*.pdf")
        if ".backup." not in path.name and not re.search(r"\.\d+\.pdf$", path.name)
    )
    if len(matches) == 1:
        return matches[0].resolve(), None
    if len(matches) > 1:
        return None, "mais de um resp-*.pdf; informe/publicar depois com --answers-pdf"
    return None, None


def analyze_lesson(lesson_dir: Path, config_path: Path) -> LessonCandidate:
    warnings: list[str] = []
    source_html, source_pdf, html_value = resolve_lesson_files(lesson_dir, config_path)
    answers_pdf, answers_warning = find_answers_pdf(lesson_dir)
    if answers_warning:
        warnings.append(answers_warning)

    expected_html_value = html_value
    if expected_html_value is None:
        context = publish.infer_lesson_context(lesson_dir)
        if context:
            expected_html_value = f"content/aulas/{context.content_group}/{lesson_dir.name}/{source_html.name}"
        else:
            warnings.append("disciplina nao inferida; sera necessario informar manualmente")

    in_content = bool(expected_html_value and (REPO_ROOT / expected_html_value).exists())
    title = config_lesson_name(config_path, html_value) if html_value else None
    if not title:
        title = extract_lesson_title(source_html, lesson_dir.name.replace("-", " "))
    return LessonCandidate(
        lesson_dir=lesson_dir,
        source_html=source_html,
        source_pdf=source_pdf,
        answers_pdf=answers_pdf,
        html_value=html_value,
        expected_html_value=expected_html_value,
        in_config=html_value is not None,
        in_content=in_content,
        title=title,
        warnings=warnings,
    )


def print_lesson_table(lessons: list[LessonCandidate]) -> None:
    print("\nAulas encontradas:")
    for idx, lesson in enumerate(lessons, start=1):
        status = []
        status.append("config:sim" if lesson.in_config else "config:nao")
        status.append("content:sim" if lesson.in_content else "content:nao")
        status.append("resp:sim" if lesson.answers_pdf else "resp:nao")
        print(f"  {idx:>2}. {lesson.lesson_dir.name} | {', '.join(status)} | {lesson.title}")
        if lesson.expected_html_value:
            print(f"      destino: {lesson.expected_html_value}")
        for warning in lesson.warnings:
            print(f"      aviso: {warning}")


def choose_lessons(lessons: list[LessonCandidate]) -> list[LessonCandidate]:
    missing = [lesson for lesson in lessons if not lesson.in_config or not lesson.in_content]
    if missing:
        print("\nAulas que ainda nao estao completas no content/config:")
        for lesson in missing:
            print(f"  - {lesson.lesson_dir.name}: {lesson.title}")
        if ask_yes_no("Publicar apenas essas aulas ausentes", default=True):
            return missing

    selection = ask("Digite numeros das aulas para publicar, separados por virgula, ou 'todas'", "todas")
    if selection.lower() in {"todas", "todos", "all"}:
        return lessons

    chosen: list[LessonCandidate] = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            index = int(part)
        except ValueError as exc:
            raise publish.PublishError(f"Selecao invalida: {part}") from exc
        if index < 1 or index > len(lessons):
            raise publish.PublishError(f"Indice fora da lista: {index}")
        chosen.append(lessons[index - 1])
    return chosen


def publish_args_for_lesson(lesson: LessonCandidate, publish_answers: bool) -> list[str]:
    args = [
        str(SCRIPT_DIR / "publish_lesson.py"),
        "--lesson-dir",
        str(lesson.lesson_dir),
        "--lesson-name",
        lesson.title,
        "--skip-build",
    ]
    if publish_answers and lesson.answers_pdf:
        args.extend(["--answers-pdf", lesson.answers_pdf.name])
    return args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fluxo interativo para publicar aulas em lote.")
    parser.add_argument("--base-dir", help="Pasta da disciplina ou pasta de uma aula.")
    parser.add_argument("--allow-dirty", action="store_true", help="Permite iniciar com git sujo; commit/push automaticos ficam desativados.")
    parser.add_argument("--dry-run", action="store_true", help="Executa apenas simulacoes.")
    args = parser.parse_args(argv)

    print("Publicacao interativa de aulas")
    print("=============================")

    dirty_before = git_status_short()
    can_commit = True
    if dirty_before:
        print("\nO repositorio ja possui alteracoes pendentes:")
        print(dirty_before)
        if not args.allow_dirty:
            raise publish.PublishError("Comece com o repositorio limpo ou use --allow-dirty.")
        print("Modo --allow-dirty ativo: o script nao fara commit/push automaticos.")
        can_commit = False

    base_dir = Path(args.base_dir or ask("Caminho da pasta da disciplina/aula")).expanduser().resolve()
    config_path = REPO_ROOT / "config.yaml"

    lesson_dirs = discover_lesson_dirs(base_dir)
    if not lesson_dirs:
        raise publish.PublishError(f"Nenhuma aula com HTML/PDF principal encontrada em {base_dir}.")

    lessons: list[LessonCandidate] = []
    skipped: list[tuple[Path, str]] = []
    for path in lesson_dirs:
        try:
            lessons.append(analyze_lesson(path, config_path))
        except publish.PublishError as exc:
            skipped.append((path, str(exc)))

    print(f"\nForam encontradas {len(lessons)} aula(s) seguindo o padrao.")
    if skipped:
        print(f"{len(skipped)} pasta(s) foram ignoradas por ambiguidade:")
        for path, reason in skipped:
            print(f"  - {path.name}: {reason}")
    print_lesson_table(lessons)
    if not lessons:
        raise publish.PublishError("Nenhuma aula publicavel encontrada apos a analise.")

    selected = choose_lessons(lessons)
    if not selected:
        print("Nenhuma aula selecionada.")
        return 0

    publish_answers = ask_yes_no("Enviar PDF de respostas quando houver resp-*.pdf", default=True)

    print("\nPlano de publicacao:")
    for lesson in selected:
        suffix = " + respostas" if publish_answers and lesson.answers_pdf else ""
        print(f"  - {lesson.lesson_dir.name}: {lesson.title}{suffix}")

    if not ask_yes_no("Rodar dry-run de cada aula agora", default=True):
        raise publish.PublishError("Fluxo interrompido antes do dry-run.")

    for lesson in selected:
        run(["python3", *publish_args_for_lesson(lesson, publish_answers), "--dry-run"], dry_run=args.dry_run)

    if not ask_yes_no("Dry-run conferido. Fazer upload real/copia/YAML agora", default=False):
        print("Fluxo interrompido antes de alterar arquivos.")
        return 0

    for lesson in selected:
        run(["python3", *publish_args_for_lesson(lesson, publish_answers)], dry_run=args.dry_run)

    if ask_yes_no("Rodar build completo do site", default=True):
        run(["python3", "build.py", "--full"], dry_run=args.dry_run)

    print("\nGit status apos publicacao:")
    status_after = git_status_short()
    print(status_after or "(limpo)")

    if not can_commit:
        print("Commit/push automaticos desativados porque o repositorio iniciou sujo.")
        return 0

    if ask_yes_no("Fazer commit dessas alteracoes", default=True):
        message = ask("Mensagem do commit", f"Publica {len(selected)} aula(s)")
        run(["git", "add", "-A"], dry_run=args.dry_run)
        run(["git", "commit", "-m", message], dry_run=args.dry_run)
        if ask_yes_no("Fazer push agora", default=False):
            run(["git", "push"], dry_run=args.dry_run)

    print("Fluxo concluido.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (publish.PublishError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
