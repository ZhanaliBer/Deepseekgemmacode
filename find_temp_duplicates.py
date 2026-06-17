from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
SIMILARITY_THRESHOLD = 0.96


def get_document_name(file_path):
    name = file_path.stem
    return re.sub(r"^\d+\s*", "", name).strip()


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def are_similar(first_text, second_text):
    if not first_text and not second_text:
        return True
    if not first_text or not second_text:
        return False

    ratio = SequenceMatcher(None, first_text, second_text).ratio()
    return ratio >= SIMILARITY_THRESHOLD


def find_similar_groups(file_texts):
    parent = {file_name: file_name for file_name in file_texts}

    def find(file_name):
        while parent[file_name] != file_name:
            parent[file_name] = parent[parent[file_name]]
            file_name = parent[file_name]
        return file_name

    def union(first_file, second_file):
        first_root = find(first_file)
        second_root = find(second_file)
        if first_root != second_root:
            parent[second_root] = first_root

    file_names = list(file_texts)
    for first_index, first_file in enumerate(file_names):
        for second_file in file_names[first_index + 1:]:
            if are_similar(file_texts[first_file], file_texts[second_file]):
                union(first_file, second_file)

    groups = defaultdict(list)
    for file_name in file_names:
        groups[find(file_name)].append(file_name)

    return [sorted(files) for files in groups.values() if len(files) > 1]


def main():
    if not TEMP_DIR.exists():
        print(f"Папка не найдена: {TEMP_DIR}")
        return

    files_by_name = defaultdict(list)
    for file_path in TEMP_DIR.glob("*.txt"):
        files_by_name[get_document_name(file_path)].append(file_path)

    duplicate_groups = []

    for document_name, file_paths in files_by_name.items():
        if len(file_paths) < 2:
            continue

        file_texts = {}
        for file_path in file_paths:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            file_texts[file_path.name] = normalize_text(text)

        for duplicate_files in find_similar_groups(file_texts):
            duplicate_groups.append((document_name, duplicate_files))

    print(f"Порог похожести: {SIMILARITY_THRESHOLD}")
    print(f"Найдено групп дублей: {len(duplicate_groups)}")

    duplicate_files_count = sum(len(files) for _, files in duplicate_groups)
    print(f"Файлов в дублях: {duplicate_files_count}")

    for index, (document_name, files) in enumerate(duplicate_groups, 1):
        print(f"\n{index}. {document_name}")
        for file_name in files:
            print(f"   - {file_name}")


if __name__ == "__main__":
    main()
