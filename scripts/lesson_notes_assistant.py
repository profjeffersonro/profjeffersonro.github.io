#!/usr/bin/env python3
"""
Assistente para adicionar notas de aula ao GitHub Pages.

O assistente faz a triagem das pastas de aula, mostra um plano, executa um
dry-run obrigatório e delega a publicação real ao publish_lesson.py.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import publish_lesson as publish  # noqa: E402


@dataclass(frozen=True)
class ConfigIndex:
    html_values: set[str]
    html_by_filename: dict[str, list[str]]
    discipline_by_group: dict[str, str]
    groups_by_discipline: dict[str, list[str]]


@dataclass
class NotePlan:
    lesson_dir: Path
    source_html: Path
    source_pdf: Path
    answers_pdf: Path | None
    title: str
    html_value: str
    discipline_name: str | None
    content_group: str | None
    already_in_config: bool
    already_in_content: bool
    warnings: list[str]

    @property
    def needs_publish(self) -> bool:
        return not self.already_in_config or not self.already_in_content

    @property
    def ready(self) -> bool:
        return bool(self.discipline_name and self.content_group and not self.warnings)


class AssistantError(RuntimeError):
    pass


DEFAULT_CONTEXTS: tuple[tuple[str, publish.LessonContext], ...] = (
    ("FM1", publish.LessonContext("Física Moderna 1", "ES-FM1")),
    ("MecFlu", publish.LessonContext("Mecânica dos Fluidos", "ES-MecFlu")),
    ("EM-Termo1", publish.LessonContext("Termodinâmica", "EM-Termo1")),
    ("Termo1", publish.LessonContext("Termodinâmica", "EM-Termo1")),
    ("EM-Termo2", publish.LessonContext("Termodinâmica", "EM-Termo2")),
    ("Termo2", publish.LessonContext("Termodinâmica", "EM-Termo2")),
    ("EM-Ondas", publish.LessonContext("Ondulatória", "EM-Ondas")),
    ("Ondas", publish.LessonContext("Ondulatória", "EM-Ondas")),
)


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


def ask_choice(prompt: str, choices: list[tuple[str, str]], default: str) -> str:
    valid = {key for key, _ in choices}
    if default not in valid:
        raise AssistantError(f"Opcao padrao invalida: {default}")

    print(prompt)
    for key, description in choices:
        marker = " [padrao]" if key == default else ""
        print(f"  {key}. {description}{marker}")
    while True:
        value = input("Escolha: ").strip().lower() or default
        if value in valid:
            return value
        print("Opcao invalida.")


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print("$ " + " ".join(shlex.quote(part) for part in cmd), flush=True)
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


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip() or "(detached HEAD)"


def resolve_dirty_start(args: argparse.Namespace, dirty_before: str) -> str:
    if not dirty_before:
        return ""

    print("\nO repositorio possui alteracoes pendentes:")
    print(dirty_before)

    if args.commit_current_state:
        choice = "commit-now"
    elif args.allow_dirty:
        choice = "include-final" if args.commit_existing_changes else "continue-no-git"
    else:
        answer = ask_choice(
            "\nComo deseja tratar o estado atual do Git antes de publicar novas notas?",
            [
                ("1", "Fazer commit do estado atual agora e continuar com o repositorio limpo"),
                ("2", "Continuar, mas bloquear commit/push automaticos no final"),
                ("3", "Continuar e incluir tambem essas alteracoes no commit final"),
                ("4", "Parar para revisar manualmente"),
            ],
            "1",
        )
        choice = {
            "1": "commit-now",
            "2": "continue-no-git",
            "3": "include-final",
            "4": "stop",
        }[answer]

    if choice == "stop":
        raise AssistantError("Fluxo interrompido para revisao manual do Git.")

    if choice == "continue-no-git":
        args.allow_dirty = True
        args.commit_existing_changes = False
        print("Continuando; commit/push automaticos ficarao bloqueados para nao misturar alteracoes antigas.")
        return dirty_before

    if choice == "include-final":
        args.allow_dirty = True
        args.commit_existing_changes = True
        print("Continuando; o commit final podera incluir tambem as alteracoes que ja existiam.")
        return dirty_before

    if choice == "commit-now":
        default_message = "Atualiza estado atual do portal"
        message = args.current_state_message or (default_message if args.yes else ask("Mensagem do commit atual", default_message))
        run(["git", "add", "-A"], dry_run=args.dry_run)
        run(["git", "commit", "-m", message], dry_run=args.dry_run)
        if not args.no_push:
            branch = git_current_branch() if not args.dry_run else "(branch atual)"
            if args.yes or ask_yes_no(f"Fazer push desse commit atual para o GitHub ({branch})", default=False):
                run(["git", "push"], dry_run=args.dry_run)
        refreshed = git_status_short() if not args.dry_run else ""
        if refreshed:
            print("\nAinda ha alteracoes pendentes apos o commit atual:")
            print(refreshed)
            args.allow_dirty = True
            args.commit_existing_changes = False
            return refreshed
        print("Estado atual salvo no Git. Continuando com o fluxo das notas.")
        return ""

    raise AssistantError(f"Opcao inesperada: {choice}")


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


def load_config_index(config_path: Path) -> ConfigIndex:
    html_values: set[str] = set()
    html_by_filename: dict[str, list[str]] = {}
    discipline_by_group: dict[str, str] = {}
    groups_by_discipline: dict[str, list[str]] = {}
    current_discipline: str | None = None

    discipline_re = re.compile(r'^\s*-\s+disciplina:\s*["\']?([^"\']+)["\']?\s*$')
    html_re = re.compile(r'^\s*html:\s*["\']?([^"\'\n]+)["\']?\s*$')

    for line in config_path.read_text(encoding="utf-8").splitlines():
        discipline_match = discipline_re.match(line)
        if discipline_match:
            current_discipline = discipline_match.group(1)
            groups_by_discipline.setdefault(current_discipline, [])
            continue

        html_match = html_re.match(line)
        if not html_match:
            continue

        html_value = html_match.group(1)
        html_values.add(html_value)
        html_by_filename.setdefault(Path(html_value).name, []).append(html_value)
        parts = Path(html_value).parts
        if len(parts) >= 3 and parts[0] == "content" and parts[1] == "aulas":
            group = parts[2]
            if current_discipline:
                discipline_by_group.setdefault(group, current_discipline)
                groups = groups_by_discipline.setdefault(current_discipline, [])
                if group not in groups:
                    groups.append(group)

    return ConfigIndex(
        html_values=html_values,
        html_by_filename=html_by_filename,
        discipline_by_group=discipline_by_group,
        groups_by_discipline=groups_by_discipline,
    )


def discover_lesson_dirs(base_path: Path) -> list[Path]:
    base_path = base_path.expanduser().resolve()
    if not base_path.exists():
        raise AssistantError(f"Pasta nao encontrada: {base_path}")
    if not base_path.is_dir():
        raise AssistantError(f"Caminho nao e pasta: {base_path}")

    try:
        source_pdf = publish.resolve_source_pdf(base_path, None, None)
        publish.resolve_source_html(base_path, None, source_pdf)
        return [base_path]
    except publish.PublishError:
        pass

    candidates: list[Path] = []
    for child in sorted((p for p in base_path.iterdir() if p.is_dir()), key=lesson_sort_key):
        if not re.search(r"aula[- _]?\d+", child.name, flags=re.IGNORECASE):
            continue
        if list(child.glob("*.html")) and list(child.glob("*.pdf")):
            candidates.append(child)
    return candidates


def resolve_lesson_files(lesson_dir: Path, index: ConfigIndex) -> tuple[Path, Path, str | None]:
    try:
        source_pdf = publish.resolve_source_pdf(lesson_dir, None, None)
        source_html = publish.resolve_source_html(lesson_dir, None, source_pdf)
        matches = index.html_by_filename.get(source_html.name, [])
        if len(matches) > 1:
            raise AssistantError(f"mais de uma entrada no config.yaml usa {source_html.name}")
        return source_html, source_pdf, matches[0] if matches else None
    except publish.PublishError as exc:
        raise AssistantError(str(exc)) from exc


def find_answers_pdf(lesson_dir: Path) -> tuple[Path | None, str | None]:
    matches = sorted(
        path
        for path in lesson_dir.glob("resp-*.pdf")
        if ".backup." not in path.name and not re.search(r"\.\d+\.pdf$", path.name)
    )
    if len(matches) == 1:
        return matches[0].resolve(), None
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        return None, f"mais de um resp-*.pdf encontrado: {names}"
    return None, None


def infer_context(lesson_dir: Path, index: ConfigIndex) -> publish.LessonContext | None:
    lesson_path = lesson_dir.as_posix()
    for group, discipline in sorted(index.discipline_by_group.items(), key=lambda item: len(item[0]), reverse=True):
        if group in lesson_path:
            return publish.LessonContext(discipline, group)
    for needle, context in DEFAULT_CONTEXTS:
        if needle in lesson_path:
            return context
    return publish.infer_lesson_context(lesson_dir)


def expected_html_value(context: publish.LessonContext, lesson_dir: Path, source_html: Path) -> str:
    return f"content/aulas/{context.content_group}/{lesson_dir.name}/{source_html.name}"


def build_note_plan(lesson_dir: Path, index: ConfigIndex) -> NotePlan:
    warnings: list[str] = []
    source_html, source_pdf, existing_html = resolve_lesson_files(lesson_dir, index)
    answers_pdf, answers_warning = find_answers_pdf(lesson_dir)
    if answers_warning:
        warnings.append(answers_warning)

    context = infer_context(lesson_dir, index)
    if existing_html:
        html_value = existing_html
        parts = Path(existing_html).parts
        content_group = parts[2] if len(parts) >= 3 and parts[0] == "content" and parts[1] == "aulas" else None
        discipline_name = index.discipline_by_group.get(content_group or "")
    elif context:
        html_value = expected_html_value(context, lesson_dir, source_html)
        discipline_name = context.discipline_name
        content_group = context.content_group
    else:
        html_value = ""
        discipline_name = None
        content_group = None
        warnings.append("disciplina/grupo de content nao inferido")

    already_in_content = bool(html_value and (REPO_ROOT / html_value).exists())
    return NotePlan(
        lesson_dir=lesson_dir,
        source_html=source_html,
        source_pdf=source_pdf,
        answers_pdf=answers_pdf,
        title=extract_lesson_title(source_html, lesson_dir.name),
        html_value=html_value,
        discipline_name=discipline_name,
        content_group=content_group,
        already_in_config=existing_html is not None,
        already_in_content=already_in_content,
        warnings=warnings,
    )


def print_plan_table(plans: list[NotePlan]) -> None:
    print("\nNotas de aula encontradas:")
    for idx, plan in enumerate(plans, start=1):
        status = [
            "config:sim" if plan.already_in_config else "config:nao",
            "content:sim" if plan.already_in_content else "content:nao",
            "resp:sim" if plan.answers_pdf else "resp:nao",
        ]
        print(f"  {idx:>2}. {plan.lesson_dir.name} | {', '.join(status)} | {plan.title}")
        if plan.html_value:
            print(f"      destino: {plan.html_value}")
        if plan.discipline_name and plan.content_group:
            print(f"      disciplina: {plan.discipline_name} / {plan.content_group}")
        for warning in plan.warnings:
            print(f"      aviso: {warning}")


def choose_plans(plans: list[NotePlan], selection: str | None) -> list[NotePlan]:
    if selection:
        raw = selection
    else:
        missing = [plan for plan in plans if plan.needs_publish]
        if missing:
            print("\nSugestao: publicar apenas as notas ausentes ou incompletas.")
            if ask_yes_no("Usar esta selecao sugerida", default=True):
                return missing
        raw = ask("Digite numeros separados por virgula, ou 'todas'", "todas")

    if raw.lower() in {"todas", "todos", "all"}:
        return plans

    chosen: list[NotePlan] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            index = int(part)
        except ValueError as exc:
            raise AssistantError(f"Selecao invalida: {part}") from exc
        if index < 1 or index > len(plans):
            raise AssistantError(f"Indice fora da lista: {index}")
        chosen.append(plans[index - 1])
    return chosen


def publish_command(
    plan: NotePlan,
    *,
    include_answers: bool,
    release_answers: bool,
    answers_drive_folder: str | None,
    skip_build: bool,
) -> list[str]:
    if not plan.discipline_name or not plan.content_group:
        raise AssistantError(f"Faltam disciplina/grupo para {plan.lesson_dir}")

    cmd = [
        "python3",
        str(SCRIPT_DIR / "publish_lesson.py"),
        "--lesson-dir",
        str(plan.lesson_dir),
        "--lesson-name",
        plan.title,
        "--discipline-name",
        plan.discipline_name,
        "--content-group",
        plan.content_group,
        "--content-html",
        plan.html_value,
    ]
    if skip_build:
        cmd.append("--skip-build")
    if include_answers and plan.answers_pdf:
        cmd.extend(["--answers-pdf", plan.answers_pdf.name])
        if release_answers:
            cmd.append("--answers-released")
        if answers_drive_folder:
            cmd.extend(["--answers-drive-folder", answers_drive_folder])
    return cmd


def commit_and_maybe_push(
    *,
    selected: list[NotePlan],
    dirty_before: str,
    allow_dirty: bool,
    commit_existing_changes: bool,
    no_commit: bool,
    no_push: bool,
    yes: bool,
    message: str | None,
    dry_run: bool,
) -> None:
    status_after = git_status_short()
    print("\nGit status apos a publicacao:")
    print(status_after or "(limpo)")

    if not status_after:
        print("Nao ha alteracoes para commit.")
        return

    if no_commit:
        print("Commit ignorado por --no-commit.")
        return

    if dirty_before and not commit_existing_changes:
        print("\nO repositorio ja estava sujo antes do assistente.")
        print("Para evitar misturar alteracoes antigas, commit/push automaticos ficam bloqueados.")
        print("Use --commit-existing-changes se quiser que o assistente inclua todo o estado atual no commit.")
        return

    if dirty_before and not allow_dirty:
        raise AssistantError("Estado inconsistente: repositorio sujo sem --allow-dirty.")

    default_message = f"Publica {len(selected)} nota(s) de aula"
    commit_message = message or default_message
    should_commit = yes or ask_yes_no("Fazer commit das alteracoes listadas", default=True)
    if not should_commit:
        print("Commit nao executado.")
        return

    if not message and not yes:
        commit_message = ask("Mensagem do commit", default_message)

    run(["git", "add", "-A"], dry_run=dry_run)
    run(["git", "commit", "-m", commit_message], dry_run=dry_run)

    if no_push:
        print("Push ignorado por --no-push.")
        return

    branch = git_current_branch() if not dry_run else "(branch atual)"
    should_push = yes or ask_yes_no(f"Fazer push para o GitHub agora ({branch})", default=True)
    if should_push:
        run(["git", "push"], dry_run=dry_run)
    else:
        print("Push nao executado.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assistente para adicionar notas de aula ao GitHub Pages.")
    parser.add_argument("base_dir", nargs="?", help="Pasta de uma aula ou pasta contendo varias aulas.")
    parser.add_argument("--select", help="Numeros das aulas separados por virgula, ou 'todas'.")
    parser.add_argument("--plan-only", action="store_true", help="Apenas analisa e mostra o plano.")
    parser.add_argument("--publish", action="store_true", help="Permite publicacao real apos o dry-run.")
    parser.add_argument("--yes", action="store_true", help="Confirma automaticamente publicacao, commit e push.")
    parser.add_argument("--include-answers", action="store_true", help="Inclui o unico resp-*.pdf encontrado.")
    parser.add_argument("--release-answers", action="store_true", help="Libera respostas no portal.")
    parser.add_argument("--answers-drive-folder", help="Pasta do Drive para respostas, relativa ao drive_folder_id.")
    parser.add_argument("--skip-build", action="store_true", help="Nao roda build.py durante cada publicacao.")
    parser.add_argument("--build-after", action="store_true", help="Roda um build.py --full ao final.")
    parser.add_argument("--allow-dirty", action="store_true", help="Permite iniciar com git sujo.")
    parser.add_argument(
        "--commit-existing-changes",
        action="store_true",
        help="Com --allow-dirty, permite incluir tambem alteracoes que ja existiam antes.",
    )
    parser.add_argument("--commit-current-state", action="store_true", help="Se o repositorio estiver sujo, commita o estado atual antes de continuar.")
    parser.add_argument("--current-state-message", help="Mensagem para o commit preparatorio do estado atual.")
    parser.add_argument("--no-commit", action="store_true", help="Publica, mas nao faz commit.")
    parser.add_argument("--no-push", action="store_true", help="Faz commit, mas nao faz push.")
    parser.add_argument("--message", help="Mensagem de commit.")
    parser.add_argument("--dry-run", action="store_true", help="Simula tambem as acoes do proprio assistente.")
    args = parser.parse_args(argv)

    if args.yes and not args.publish:
        args.publish = True
    if args.no_commit:
        args.no_push = True
    if args.no_commit and args.message:
        raise AssistantError("--message nao faz sentido junto com --no-commit.")
    if args.current_state_message and not args.commit_current_state:
        args.commit_current_state = True

    print("Assistente CLI de notas de aula")
    print("===============================")

    dirty_before = resolve_dirty_start(args, git_status_short())

    base_dir = Path(args.base_dir or ask("Caminho da pasta da disciplina/aula")).expanduser().resolve()
    config_path = REPO_ROOT / "config.yaml"
    index = load_config_index(config_path)

    lesson_dirs = discover_lesson_dirs(base_dir)
    if not lesson_dirs:
        raise AssistantError(f"Nenhuma pasta de aula com HTML/PDF encontrada em {base_dir}.")

    plans: list[NotePlan] = []
    skipped: list[tuple[Path, str]] = []
    for lesson_dir in lesson_dirs:
        try:
            plans.append(build_note_plan(lesson_dir, index))
        except AssistantError as exc:
            skipped.append((lesson_dir, str(exc)))

    print(f"\nForam analisadas {len(plans)} nota(s) de aula.")
    if skipped:
        print(f"{len(skipped)} pasta(s) foram ignoradas:")
        for path, reason in skipped:
            print(f"  - {path.name}: {reason}")
    print_plan_table(plans)
    if not plans:
        raise AssistantError("Nenhuma nota publicavel encontrada.")

    selected = choose_plans(plans, args.select)
    if not selected:
        print("Nenhuma nota selecionada.")
        return 0

    not_ready = [plan for plan in selected if not plan.ready]
    if not_ready:
        print("\nEstas notas precisam de ajuste manual antes de publicar:")
        for plan in not_ready:
            print(f"  - {plan.lesson_dir.name}: {', '.join(plan.warnings) or 'dados incompletos'}")
        return 1

    include_answers = args.include_answers
    if not include_answers and any(plan.answers_pdf for plan in selected) and not args.yes:
        include_answers = ask_yes_no("Incluir PDFs resp-*.pdf quando houver", default=False)
    release_answers = args.release_answers
    if include_answers and not release_answers and not args.yes:
        release_answers = ask_yes_no("Liberar respostas no portal agora", default=False)

    answers_drive_folder = args.answers_drive_folder
    if include_answers and not answers_drive_folder and not args.yes:
        if ask_yes_no("Usar uma pasta unica no Drive para respostas", default=True):
            answers_drive_folder = ask("Pasta de respostas relativa ao drive_folder_id", "Respostas")

    print("\nPlano escolhido:")
    for plan in selected:
        suffix = ""
        if include_answers and plan.answers_pdf:
            suffix = " + respostas"
            suffix += " liberadas" if release_answers else " nao liberadas"
        print(f"  - {plan.lesson_dir.name}: {plan.title}{suffix}")

    print("\nDry-run obrigatorio:")
    for plan in selected:
        run(
            [
                *publish_command(
                    plan,
                    include_answers=include_answers,
                    release_answers=release_answers,
                    answers_drive_folder=answers_drive_folder,
                    skip_build=True,
                ),
                "--dry-run",
            ],
            dry_run=args.dry_run,
        )

    if args.plan_only:
        print("Plano concluido; nenhuma publicacao real foi executada.")
        return 0

    do_publish = args.publish
    if not do_publish and not args.yes:
        do_publish = ask_yes_no("Dry-run conferido. Publicar agora", default=False)
    if not do_publish:
        print("Publicacao real nao executada.")
        return 0

    print("\nPublicacao real:")
    for plan in selected:
        run(
            publish_command(
                plan,
                include_answers=include_answers,
                release_answers=release_answers,
                answers_drive_folder=answers_drive_folder,
                skip_build=args.skip_build or args.build_after,
            ),
            dry_run=args.dry_run,
        )

    if args.build_after:
        run(["python3", "build.py", "--full"], dry_run=args.dry_run)

    commit_and_maybe_push(
        selected=selected,
        dirty_before=dirty_before,
        allow_dirty=args.allow_dirty,
        commit_existing_changes=args.commit_existing_changes,
        no_commit=args.no_commit,
        no_push=args.no_push,
        yes=args.yes,
        message=args.message,
        dry_run=args.dry_run,
    )
    print("Fluxo concluido.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssistantError, publish.PublishError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        sys.stdout.flush()
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
