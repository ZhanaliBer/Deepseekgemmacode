from pathlib import Path
import json
import re
import shutil

import fitz


BASE_DIR = Path(__file__).resolve().parent
FORMAT_FILE = BASE_DIR / "structure.json"
SOURCE_DIR = BASE_DIR / "berik"
RESULT_DIR = BASE_DIR / "result"
MAX_PREFIX_LENGTH = 80


def extract_source_number(file_path):
    match = re.search(r'_(\d+)', file_path.stem)
    if match:
        return int(match.group(1))

    if file_path.stem.isdigit():
        return int(file_path.stem)

    return None


def normalize_source_pdfs():
    created = 0
    for source_path in list(SOURCE_DIR.glob("*.pdf")):
        if source_path.stem.isdigit():
            continue

        number = extract_source_number(source_path)
        if number is None:
            continue

        normalized_path = SOURCE_DIR / f"{number}.pdf"
        if normalized_path.exists():
            continue

        source_path.rename(normalized_path)
        created += 1

    if created:
        print(f"Нормализовано PDF-файлов: {created}")


def merge_pdfs(pdf_numbers, output_path):
    result_pdf = fitz.open()

    try:
        for pdf_number in pdf_numbers:
            source_path = SOURCE_DIR / f"{pdf_number}.pdf"
            if not source_path.exists():
                raise FileNotFoundError(f"PDF не найден: {source_path}")

            with fitz.open(source_path) as source_pdf:
                result_pdf.insert_pdf(source_pdf)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_pdf.save(output_path)
    finally:
        result_pdf.close()


def numbered_name(number, name):
    return f"{number}. {name}"


def pdf_numbers_prefix(pdf_numbers):
    if not pdf_numbers:
        return "0"

    ranges = []
    start = pdf_numbers[0]
    previous = pdf_numbers[0]

    for number in pdf_numbers[1:]:
        if number == previous + 1:
            previous = number
            continue

        ranges.append((start, previous))
        start = number
        previous = number

    ranges.append((start, previous))

    prefix = "_".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in ranges
    )

    if len(prefix) > MAX_PREFIX_LENGTH:
        prefix = f"{pdf_numbers[0]}-{pdf_numbers[-1]}_count{len(pdf_numbers)}"

    return prefix


def main():
    with FORMAT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    normalize_source_pdfs()

    if RESULT_DIR.exists():
        shutil.rmtree(RESULT_DIR)
    RESULT_DIR.mkdir(exist_ok=True)

    created = 0
    for folder_index, folder in enumerate(data["files"], 1):
        folder_path = RESULT_DIR / numbered_name(folder_index, folder["name"])
        folder_path.mkdir(parents=True, exist_ok=True)

        for document in folder["content"]:
            output_name = numbered_name(pdf_numbers_prefix(document["pdfs"]), document["name"])
            if not output_name.lower().endswith(".pdf"):
                output_name += ".pdf"

            output_path = folder_path / output_name
            merge_pdfs(document["pdfs"], output_path)
            created += 1

    print(f"Создано PDF-файлов: {created}")


if __name__ == "__main__":
    main()
