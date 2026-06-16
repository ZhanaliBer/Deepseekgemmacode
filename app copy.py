import os

import base64

import requests

import shutil

import re

import fitz

import json

import logging

import pandas as pd

from pathlib import Path

from dotenv import load_dotenv

from concurrent.futures import ThreadPoolExecutor

import urllib3

from requests.adapters import HTTPAdapter

from urllib3.util.retry import Retry



# Отключаем предупреждения о небезопасном соединении

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



load_dotenv()

OCR_KEY = os.getenv("OCR_KEY", "sk-YkWj7z0GvobZjkGSDcZnTQ")      

GEMMA_KEY = os.getenv("GEMMA_KEY", "sk-fbC7zz7k4rX5mvQsdA7IcA")    

URL = os.getenv("AI_URL", "https://llm.alem.ai/v1/chat/completions")

MAX_WORKERS = int(os.getenv("MAX_WORKERS", 5))



# Локальные папки для работы в IDE

BASE_DIR = Path(__file__).parent.resolve()

INPUT_DIR = BASE_DIR / "berik"  

OUTPUT_DIR = BASE_DIR / "docs"  

EXCEL_FILE = BASE_DIR / "types.xlsx"



# Умная сессия с автоматическими повторами

session = requests.Session()

retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])

session.mount('https://', HTTPAdapter(max_retries=retries))



def sanitize_folder_name(name):

    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)

    return cleaned.strip()



def get_file_as_base64(file_path):

    if str(file_path).lower().endswith('.pdf'):

        doc = fitz.open(file_path)

        page = doc.load_page(0)

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        img_bytes = pix.tobytes("jpeg")

        doc.close()

        return base64.b64encode(img_bytes).decode('utf-8')

    else:

        with open(file_path, "rb") as f:

            return base64.b64encode(f.read()).decode('utf-8')



def ocr_image_to_text(file_path):

    img_b64 = get_file_as_base64(file_path)

    payload = {

        "model": "deepseek-ocr",

        "messages": [{"role": "user", "content": [

            {"type": "text", "text": "Extract all text from this image. Return ONLY the text."},

            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}

        ]}],

        "temperature": 0.0,

        "max_tokens": 3000  

    }

    headers = {"Authorization": f"Bearer {OCR_KEY}", "Content-Type": "application/json"}

    resp = session.post(URL, headers=headers, json=payload, verify=False, timeout=60)

    resp.raise_for_status()

    return resp.json()["choices"][0]["message"]["content"]



def group_files_with_gemma(extracted_data):

    docs_info = ""

    for item in extracted_data:

        text = item['text']

        short_text = text[:700] + " ... " + text[-700:] if len(text) > 1400 else text

        docs_info += f"ФАЙЛ: {os.path.basename(item['filename'])}\nТЕКСТ:\n{short_text}\n\n"

       

    payload = {
        "model": "gemma4",
        "messages": [
            {"role": "system", "content": """Ты экспертный сортировщик документов. Перед тобой тексты страниц в хронологическом порядке. Твоя задача — распределить их по группам, строго соблюдая иерархию правил.

            0. АБСОЛЮТНЫЙ ПРИОРИТЕТ (МОНОЛИТ "ЗЕМЛЕУСТРОИТЕЛЬНЫЙ ПРОЕКТ"): Если ты видишь в тексте 'Землеустроительный проект' или 'Раздел 0', ты ОБЯЗАН склеить этот лист и абсолютно все последующие листы в один гигантский документ. Эта непрерывная склейка включает в себя ВСЕ листы вплоть до того файла, который идет ровно перед листом 'Бланк заказа'. Лист 'Бланк заказа' отрезается и начинает новый отдельный документ.
            
            ИГНОРИРУЙ ПРОПУСКИ: Если нумерация файлов идет так: 53 -> 55, а 54 отсутствует — это не повод разрывать проект. Считай, что 55 идет сразу после 53.
            
            1. ВЫСШИЙ ПРИОРИТЕТ РАЗДЕЛЕНИЯ (КОЛОНТИТУЛЫ И ЗАГОЛОВКИ): Вне правила 0, любые колонтитулы и заголовки ('ЗАЯВЛЕНИЕ', 'ӨТІНІШ', 'ДОГОВОР', 'АКТ', 'СПРАВКА') имеют максимальную силу. Это 100% старт нового документа. Никакие другие маркеры не могут отменить это разделение.
            
            2. ВЫСШИЙ ПРИОРИТЕТ СКЛЕЙКИ (ЛОГОТИПЫ): Если четкого титула нет, но присутствует редкий стилизованный логотип компании/проекта — эти листы 100% идут вместе. Это правило перебивает простую текстовую нумерацию или графику.
            
            3. ИСКЛЮЧЕНИЕ ДЛЯ СТАНДАРТНЫХ БЛАНКОВ: Обычные текстовые шапки (реквизиты) на заявлениях не склеивай.
            
            4. ПРОДОЛЖЕНИЕ ТЕКСТА: Если нет колонтитулов и логотипов, а текст содержит 'Страница 2' — крепи его к предыдущему файлу.
            
            5. ГРАФИКА: Файлы '[ГРАФИЧЕСКИЙ ДОКУМЕНТ: ТЕКСТ ОТСУТСТВУЕТ]' остаются одиночными (кроме случаев из пункта 0, там они вклеиваются в проект).
            Не забывай = Сначала титул, потом остальное. Огромный титул = ОТДЕЛЬНЫЙ ДОК ВНЕ ПУНКТА НОЛЬ
            Верни ТОЛЬКО валидный JSON в формате списка списков. Например: [["file1.jpg"], ["file2.jpg", "file3.jpg"]]"""},
            {"role": "user", "content": docs_info}
        ],
        "temperature": 0.0,
        "max_tokens": 1500
    }

    try:

        headers = {"Authorization": f"Bearer {GEMMA_KEY}", "Content-Type": "application/json"}

        resp = session.post(URL, headers=headers, json=payload, verify=False, timeout=60)

        resp.raise_for_status()

        answer = resp.json()["choices"][0]["message"]["content"]

        json_match = re.search(r'\[.*\]', answer, re.DOTALL)

        if json_match:

            return json.loads(json_match.group())

        return [[os.path.basename(item['filename'])] for item in extracted_data]

    except Exception as e:

        logging.error(f"Ошибка сортировки Джеммой: {e}")

        return [[os.path.basename(item['filename'])] for item in extracted_data]



def analyze_document_by_image(file_path, types_list):

    img_b64 = get_file_as_base64(file_path)

    if types_list:

        numbered_types = [f"{i+1}. {t}" for i, t in enumerate(types_list)]

        types_str = "\n".join(numbered_types)

        system_prompt = (

            f"Ты строгий визуальный классификатор документов. Перед тобой список разрешенных категорий из Excel:\n{types_str}\n\n"

            f"Внимательно посмотри на изображение документа и определи его тип. НЕ СОЗДАВАЙ ЛИШНИХ ПАПОК = ОДИНАКОВЫЕ ПАПКИ = НАДО СЛОЖИТЬ В 1 ФАЙЛ\n"

            f"Учитывай казахский язык (ӨТІНІШ -> Заявление). Если это чертеж/схема без текста — выбери подходящую категорию.\n"

            f"В качестве ответа верни ТОЛЬКО ЦИФРУ номера пункта."

        )

    else:

        system_prompt = "Посмотри на картинку и определи тип документа. Верни только одно-два слова на русском языке."



    payload = {

        "model": "gemma4",

        "messages": [{"role": "user", "content": [

            {"type": "text", "text": system_prompt},

            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}

        ]}],

        "temperature": 0.0,

        "max_tokens": 5  

    }

    try:

        headers = {"Authorization": f"Bearer {GEMMA_KEY}", "Content-Type": "application/json"}

        resp = session.post(URL, headers=headers, json=payload, verify=False, timeout=45)

        resp.raise_for_status()

        raw_answer = resp.json()["choices"][0]["message"]["content"].strip()

        match = re.search(r'\d+', raw_answer)

        if types_list and match:

            index = int(match.group(0)) - 1

            if 0 <= index < len(types_list):

                return types_list[index]

        return "НЕИЗВЕСТНО"

    except Exception as e:

        logging.error(f"Ошибка визуальной классификации: {e}")

        return "ОШИБКА"



def merge_and_save_pdfs(files_list, source_dir, target_folder, final_name):

    merged_pdf = fitz.open()

    for f_name in files_list:

        f_path = os.path.join(source_dir, f_name)

        if f_name.lower().endswith('.pdf'):

            temp_doc = fitz.open(f_path)

            merged_pdf.insert_pdf(temp_doc)

            temp_doc.close()

        else:

            img_doc = fitz.open(f_path)

            pdf_bytes = img_doc.convert_to_pdf()

            temp_doc = fitz.open("pdf", pdf_bytes)

            merged_pdf.insert_pdf(temp_doc)

            temp_doc.close()

            img_doc.close()

           

    merged_pdf.save(os.path.join(target_folder, f"{final_name}.pdf"))

    merged_pdf.close()

    return True



def main():

    INPUT_DIR.mkdir(exist_ok=True)

    OUTPUT_DIR.mkdir(exist_ok=True)

   

    valid_filenames = [f for f in os.listdir(INPUT_DIR) if os.path.isfile(os.path.join(INPUT_DIR, f)) and not f.startswith('.')]

   

    if not valid_filenames:

        logging.error(f"❌ Папка {INPUT_DIR.name} пуста. Пожалуйста, добавьте документы для сортировки.")

        return



    logging.info(f"📥 Найдено файлов для обработки: {len(valid_filenames)}")



    allowed_types = []

    if EXCEL_FILE.exists():

        try:

            df = pd.read_excel(EXCEL_FILE)

            column_name = "Название документа"

            if column_name in df.columns:

                raw_list = df[column_name].dropna().astype(str).str.strip().unique().tolist()

                allowed_types = [t for t in raw_list if t and not t.startswith("№")]

                logging.info(f"✅ Успешно загружен Excel-файл ({len(allowed_types)} категорий).")

        except Exception as e:

            logging.error(f"⚠️ Ошибка чтения Excel файла: {e}")

    else:

        logging.warning(f"⚠️ Файл {EXCEL_FILE.name} не найден. Классификация будет работать без строгого списка.")



    logging.info(f"👁️ ЭТАП 1: Запуск параллельного OCR...")

    extracted_data = []

   

    def thread_ocr_worker(f_name):

        f_path = os.path.join(INPUT_DIR, f_name)

        try:

            text = ocr_image_to_text(f_path)

            return {"filename": f_path, "text": text if text.strip() else "[ГРАФИЧЕСКИЙ ДОКУМЕНТ: ТЕКСТ ОТСУТСТВУЕТ]"}

        except:

            return None



    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        results = executor.map(thread_ocr_worker, valid_filenames)

        for res in results:

            if res is not None: extracted_data.append(res)



    logging.info("🧠 ЭТАП 2: Сортировка структуры...")

    logging.info("🧠 ЭТАП 2: Подготовка данных и сортировка...")
    
    temp_mapping = {}
    for i, item in enumerate(extracted_data):
        clean_name = f"FILE_{i:03d}.jpg"
        temp_mapping[clean_name] = os.path.basename(item['filename'])
        item['filename'] = clean_name 
    
    grouped_files = group_files_with_gemma(extracted_data)
    
    restored_grouped = []
    for group in grouped_files:
        restored_group = [temp_mapping[f] for f in group if f in temp_mapping]
        if restored_group:
            restored_grouped.append(restored_group)
    
    grouped_files = restored_grouped # Теперь используем восстановленные данные
    logging.info(f"🧩 Сформировано {len(grouped_files)} документов.")



    logging.info("📦 ЭТАП 3: Итоговая сборка...")

    for idx, group in enumerate(grouped_files, 1):

        if not group: continue

       

        # Ренж файлов для имени PDF

        nums = [int(re.search(r'\d+', f).group()) for f in group if re.search(r'\d+', f)]

        range_str = f"{min(nums)}-{max(nums)}" if len(nums) > 1 else f"{nums[0] if nums else idx}"

       

        doc_type = analyze_document_by_image(os.path.join(INPUT_DIR, group[0]), allowed_types)

       

        # Именование: "1 Название_типа"

        safe_folder = sanitize_folder_name(f"{idx} {doc_type}")

        target_folder = OUTPUT_DIR / safe_folder

        target_folder.mkdir(parents=True, exist_ok=True)

       

        merge_and_save_pdfs(group, INPUT_DIR, target_folder, f"{range_str} {doc_type}")

        logging.info(f"🗂️ Документ {idx}: Группа {range_str} сохранена как '{range_str} {doc_type}.pdf'")



    logging.info(f"🎉 ВСЕ ЭТАПЫ ЗАВЕРШЕНЫ.")



if __name__ == "__main__":

    main()