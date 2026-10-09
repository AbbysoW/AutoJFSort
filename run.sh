#!/usr/bin/env bash
# jfdump — сортировка скачанных медиафайлов в библиотеку Jellyfin через LLM.
#
#   ./run.sh [--target DIR] [--fonly | --donly] [--dry-run] PATH [PATH ...]
#
# Флаги можно ставить в любом месте (до, между и после путей).
set -euo pipefail

# ============================ Настройки ============================
TARGET="${JFDUMP_TARGET:-/mnt/jellyfin}"   # корень библиотеки по умолчанию
PYTHON="${JFDUMP_PYTHON:-}"                # по умолчанию .venv/bin/python или python3
# ===================================================================

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORIG_PWD="$PWD"

usage() {
    cat >&2 <<'EOF'
Usage: run.sh [--target DIR] [--fonly | --donly] [--dry-run] PATH [PATH ...]

  --target DIR   Jellyfin library root (overrides the default TARGET)
  --fonly        process files only (directories are ignored)
  --donly        process directories only (files are ignored)
  --dry-run      only print the mkdir/mv commands, change nothing

PATH may be a file, a directory or a glob mask. Quote masks ("dir/*") to let
jfdump expand them itself.
EOF
}

# --dry-run обрабатывает только оболочка; всё остальное уходит в main.py как есть.
DRY_RUN=0
ARGS=()
while (($#)); do
    case $1 in
        -h|--help) usage; exit 0 ;;
        --dry-run) DRY_RUN=1 ;;
        --)        ARGS+=("$@"); break ;;
        *)         ARGS+=("$1") ;;
    esac
    shift
done
((${#ARGS[@]})) || { usage; exit 2; }

if [[ -z $PYTHON ]]; then
    if [[ -x $SCRIPT_DIR/.venv/bin/python ]]; then
        PYTHON="$SCRIPT_DIR/.venv/bin/python"
    else
        PYTHON=python3
    fi
fi

# Интерактивные вопросы читаем с терминала, а не из stdin.
if ((!DRY_RUN)) && ! { true </dev/tty; } 2>/dev/null; then
    echo "jfdump: no controlling terminal for confirmations (use --dry-run)" >&2
    exit 1
fi

PLAN="$(mktemp)"
trap 'rm -f -- "$PLAN"' EXIT

export PYTHONUTF8=1

# main.py запускается из каталога проекта (.env, logs/, локальные импорты),
# поэтому исходный каталог передаётся явно — относительные пути пользователя
# разрешаются относительно него.
# --target по умолчанию идёт первым; если пользователь передал свой --target,
# argparse берёт последнее значение.
rc=0
(
    cd -- "$SCRIPT_DIR"
    exec "$PYTHON" main.py --base-dir "$ORIG_PWD" --target "$TARGET" "${ARGS[@]}"
) >"$PLAN" || rc=$?

case $rc in
    0) ;;
    1) echo "jfdump: some items were not processed (see messages above)" >&2 ;;
    *) exit "$rc" ;;
esac

if [[ ! -s $PLAN ]]; then
    echo "jfdump: nothing to move" >&2
    exit "$rc"
fi

moved=0 skipped=0 failed=0

# План: src\0dst\0src\0dst\0... — читаем через fd 3, чтобы не трогать stdin.
exec 3<"$PLAN"
while IFS= read -r -d '' src <&3 && IFS= read -r -d '' dst <&3; do
    dst_dir="${dst%/*}"

    if ((DRY_RUN)); then
        printf 'mkdir -p -- %q\n' "$dst_dir"
        printf 'mv -n -- %q %q\n' "$src" "$dst"
        continue
    fi

    if [[ ! -e $src && ! -L $src ]]; then
        echo "Source no longer exists, skipped: $src" >&2
        failed=$((failed + 1))
        continue
    fi
    if [[ -e $dst || -L $dst ]]; then
        echo "Destination already exists, skipped: $dst" >&2
        failed=$((failed + 1))
        continue
    fi

    read -r -p "Move $src to $dst [y/n]: " answer </dev/tty || answer=n
    case $answer in
        [yY]|[yY][eE][sS])
            # -n: ни при каких условиях не перезаписывать существующий файл
            if mkdir -p -- "$dst_dir" && mv -n -- "$src" "$dst"; then
                moved=$((moved + 1))
            else
                echo "Failed: $src -> $dst" >&2
                failed=$((failed + 1))
            fi
            ;;
        *)
            skipped=$((skipped + 1))
            ;;
    esac
done
exec 3<&-

if ((!DRY_RUN)); then
    echo "Done: moved=$moved skipped=$skipped failed=$failed" >&2
    ((failed == 0)) || rc=1
fi
exit "$rc"