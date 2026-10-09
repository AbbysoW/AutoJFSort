#!/usr/bin/env python3
"""jfdump: Python-часть (точка входа).

Контракт с run.sh:
  * stdout  — ТОЛЬКО план перемещений: `src\\0dst\\0src\\0dst\\0...` (абсолютные пути).
              NUL-разделитель — единственный способ безопасно передать любые имена
              (пробелы, кавычки, переводы строк, кириллицу).
  * stderr  — логи, прогресс, предупреждения (всё, что печатают pipeline/send_request
              в stdout, тоже перенаправляется сюда).
  * код возврата: 0 — ок, 1 — часть элементов не обработана (план всё равно выведен),
                  2 — ошибка аргументов (argparse), 3 — фатальная ошибка.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import logging
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FATAL = 3

logger = logging.getLogger("jfdump")


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jfdump",
        description="Sort downloaded media into a Jellyfin library using an LLM.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="files, directories or glob masks (quote a mask to expand it here, "
        "not in the shell)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("JFDUMP_TARGET"),
        metavar="PATH",
        help="Jellyfin library root (overrides the default TARGET from run.sh)",
    )
    parser.add_argument("--base-dir", default=os.getcwd(), help=argparse.SUPPRESS)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fonly", action="store_true", help="process files only, ignore directories")
    mode.add_argument("--donly", action="store_true", help="process directories only, ignore files")
    return parser


# ---------------------------------------------------------------- paths
def abs_path(base: str, p: str) -> str:
    """Абсолютный нормализованный путь без разыменования симлинков."""
    return os.path.abspath(os.path.join(base, os.path.expanduser(p)))


def expand_arg(arg: str, base: str) -> list[Path]:
    """Один аргумент -> список путей. Существующий путь имеет приоритет над маской."""
    expanded = os.path.expanduser(arg)
    literal = os.path.join(base, expanded)
    if os.path.lexists(literal):
        return [Path(os.path.abspath(literal))]
    if glob.has_magic(expanded):
        pattern = expanded if os.path.isabs(expanded) else os.path.join(glob.escape(base), expanded)
        return [Path(os.path.abspath(m)) for m in sorted(glob.glob(pattern, recursive=True))]
    return []


def collect_items(args: argparse.Namespace, root: Path) -> tuple[list[Path], bool]:
    """Раскрывает маски, применяет --fonly/--donly, отсеивает опасное. -> (items, ok)."""
    items: list[Path] = []
    seen: set[Path] = set()
    ok = True

    for arg in args.paths:
        if not arg:
            logger.warning("Empty path argument ignored")
            continue
        matches = expand_arg(arg, args.base_dir)
        if not matches:
            logger.warning("No match for %r", arg)
            ok = False
            continue

        for path in matches:
            if path in seen:
                continue
            seen.add(path)

            is_dir = path.is_dir()
            if not is_dir and not path.is_file():
                logger.warning("Not a regular file or directory, skipped: %s", path)
                continue
            if args.fonly and is_dir:
                logger.debug("--fonly: directory ignored: %s", path)
                continue
            if args.donly and not is_dir:
                logger.debug("--donly: file ignored: %s", path)
                continue

            # Защита от обработки самой библиотеки (иначе rglob утянет весь каталог Jellyfin).
            resolved = path.resolve()
            if resolved.is_relative_to(root):
                logger.warning("Already inside the library, skipped: %s", path)
                continue
            if is_dir and root.is_relative_to(resolved):
                logger.warning("Directory contains the library, skipped: %s", path)
                continue

            items.append(path)
    return items, ok


# ---------------------------------------------------------------- validation
def resolve_pairs(item: Path, transformations: dict[Path, Path]) -> list[tuple[Path, Path]]:
    """Превращает ответ pipeline в пары (абсолютный src, dst), отбрасывая «галлюцинации»."""
    if item.is_dir():
        # pipeline для папки возвращает пути относительно этой папки
        pairs = []
        for rel, dst in transformations.items():
            src = Path(os.path.normpath(item / rel))
            if not src.is_relative_to(item) or not src.is_file():
                logger.warning("LLM returned unknown source, skipped: %s", rel)
                continue
            pairs.append((src, dst))
        return pairs

    # Одиночный файл: ожидаем ровно одну запись про него.
    for src, dst in transformations.items():
        if Path(os.path.normpath(src)) == item:
            return [(item, dst)]
    if len(transformations) == 1:
        (_, dst), = transformations.items()
        return [(item, dst)]
    logger.warning("Unexpected LLM answer for %s, skipped", item)
    return []


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # intermixed: флаги допустимы в любом месте — до, между и после путей
    args = parser.parse_intermixed_args(argv)
    if not args.target:
        parser.error("--target is required (or set JFDUMP_TARGET)")

    from logger import setup_logging  # локальный пакет packages/logger

    setup_logging(service="jfdump", stream_level="WARNING")

    root = Path(abs_path(args.base_dir, args.target)).resolve()
    if not root.is_dir():
        logger.error("Target is not a directory: %s", root)
        return EXIT_FATAL

    items, ok = collect_items(args, root)
    if not items:
        print("jfdump: nothing to process", file=sys.stderr)
        return EXIT_OK if ok else EXIT_PARTIAL

    # Ленивый импорт: config.py требует LLM_API_KEY, а --help и ошибки аргументов
    # должны работать и без него.
    try:
        from pipeline import pipeline
    except Exception:
        logger.exception("Cannot initialise pipeline (check .env / llm_api_key)")
        return EXIT_FATAL

    plan: list[tuple[Path, Path]] = []
    used_src: set[Path] = set()
    used_dst: set[Path] = set()

    for n, item in enumerate(items, 1):
        print(f"[{n}/{len(items)}] {'dir ' if item.is_dir() else 'file'} {item}", file=sys.stderr)
        try:
            # send_request.py содержит отладочный print() — не даём ему испортить stdout.
            with contextlib.redirect_stdout(sys.stderr):
                transformations = pipeline(root, item)
        except Exception as exc:  # FileExistsError, ValueError, ошибки API и т.д.
            logger.error("Failed to process %s: %s", item, exc)
            logger.debug("traceback", exc_info=True)
            ok = False
            continue

        for src, dst in resolve_pairs(item, transformations):
            if src == dst:
                continue
            if src in used_src or dst in used_dst:
                logger.warning("Duplicate source/destination in plan, skipped: %s -> %s", src, dst)
                ok = False
                continue
            used_src.add(src)
            used_dst.add(dst)
            plan.append((src, dst))

    out = sys.stdout.buffer
    for src, dst in plan:
        out.write(os.fsencode(src) + b"\0" + os.fsencode(dst) + b"\0")
    out.flush()

    return EXIT_OK if ok else EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main())