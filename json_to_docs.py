from pathlib import Path
import json

import fitz


BASE_DIR = Path(__file__).resolve().parent
FORMAT_FILE = BASE_DIR / "format.json"
SOURCE_DIR = BASE_DIR / "berik"
RESULT_DIR = BASE_DIR / "result"


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


def main():
    with FORMAT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    RESULT_DIR.mkdir(exist_ok=True)

    created = 0
    for folder in data["files"]:
        folder_path = RESULT_DIR / folder["name"]
        folder_path.mkdir(parents=True, exist_ok=True)

        for document in folder["content"]:
            output_name = document["name"]
            if not output_name.lower().endswith(".pdf"):
                output_name += ".pdf"

            output_path = folder_path / output_name
            merge_pdfs(document["pdfs"], output_path)
            created += 1

    print(f"Создано PDF-файлов: {created}")


if __name__ == "__main__":
    main()
