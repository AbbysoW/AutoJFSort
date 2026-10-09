from pathlib import Path

from rapidfuzz import process, fuzz

from send_request import Request

MOVIES_DIR = "Movies"
SHOWS_DIR = "Shows" 


# LIBRARY PARSING
def scan_movies(root: Path) -> list[str]:
    movies_dir = root / MOVIES_DIR
    if not movies_dir.is_dir():
        return []
    return sorted(p.name for p in movies_dir.iterdir() if p.is_dir())


def scan_shows(root: Path) -> dict[str, list[int]]:
    shows_dir = root / SHOWS_DIR
    shows: dict[str, list[int]] = {}
    if not shows_dir.is_dir():
        return shows
    for show in sorted(p for p in shows_dir.iterdir() if p.is_dir()):
        shows[show.name] = sorted(
            s.name.split('/')[-1]
            for s in show.iterdir()
            if s.is_dir() # and s.name.startswith("Season ") and s.name.split('/')[-1].isdigit()
        )
    return shows


def scan_library(root: Path, limit: int = 5) -> dict:
    return {"Movies": scan_movies(root)[:limit], "Shows": list(scan_shows(root).items())[:limit]}


# CANDIDATE SELECTION
def library_names(lib: dict) -> list[str]:
    """Плоский список имён (фильмы + сериалы) для fuzzy-поиска."""
    return [*lib["Movies"], *lib["Shows"].keys()]


def select_candidates(query: str | Path, names: list[str], k: int = 5) -> list[str]:
    if isinstance(query, Path):
        query = query.name  # имя папки/файла, а не полный путь
    if not names or not query:
        return []
    return [
        m[0]
        for m in process.extract(query, names, scorer=fuzz.WRatio, limit=k)
    ]


# ANSWER VALIDATION
def safe_target(root: Path, rel: str | Path) -> Path:
    root = root.resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escapes library root: {rel}")
    if target.exists():
        raise FileExistsError(f"Collision: {target}")
    return target


# ENTRY POINT
def unwrap_folder(folder_path: Path) -> list[str]:
    """Всегда возвращает список файлов (относительные пути)."""
    if not folder_path.is_dir():
        return [folder_path]
    return sorted(
        str(p.relative_to(folder_path)) for p in folder_path.rglob("*") if p.is_file()
    )


def pipeline(root: Path, folder_path: Path) -> dict[Path, Path]:
    lib = scan_library(root)
    # candidates = select_candidates(folder_path, library_names(lib))
    files = unwrap_folder(folder_path)

    result = Request.process(lib, files)
    return {
        Path(src): safe_target(root, dst)
        for src, dst in result.transformations.items()
    }


if __name__ == "__main__":
    root = Path("/mnt/jellyfin-test")
    folder_path = Path("/mnt/torrent-test/complete")

    lib = scan_library(root)
    # names = library_names(lib)
    # candidates = select_candidates(folder_path, names)
    files = unwrap_folder(folder_path)

    print("lib\n", lib)
    # print("candidates\n", candidates)s
    print("files\n", files)


if __name__ == "__main__":
    root = Path("/mnt/jellyfin-test")
    test_path = Path("/mnt/torrent-test/complete/Green.Mile.1999.bdrip-avc.dexter_lex.mkv")

    trans = pipeline(root, test_path)

    print(trans)