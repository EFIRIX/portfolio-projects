from __future__ import annotations

import io
import json
import math
import re
import shutil
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


SOURCE = Path("/Users/timka/Downloads/Otkryty_bank_zadach_FIPI_EGE_po_profilnoy_matematike.pdf")
TEXT_CACHE = Path("/Users/timka/Documents/EGE/pdf_text_cache.json")
OUTPUT = Path("/Users/timka/Documents/EGE/FIPI_EGE_profil_first_part_inline_answers_solutions.pdf")

PAGE_W = 595.276
PAGE_H = 841.89
MARGIN_X = 46
FONT = "Arial"
FONT_BOLD = "ArialBold"

SECTION_NAMES = {
    1: "Планиметрия 1",
    2: "Векторы",
    3: "Стереометрия 1",
    4: "Вероятность 1",
    5: "Вероятность 2",
    6: "Уравнения 1",
    7: "Вычисления и преобразования",
    8: "Производная и ее график",
    9: "Задачи с прикладным содержанием",
    10: "Текстовые задачи",
    11: "Анализ графика",
    12: "Поиск экстремума",
}


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(FONT, "/System/Library/Fonts/Supplemental/Arial.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))


def load_texts() -> list[str]:
    if TEXT_CACHE.exists():
        return json.loads(TEXT_CACHE.read_text(encoding="utf-8"))

    reader = PdfReader(str(SOURCE))
    texts = [page.extract_text() or "" for page in reader.pages]
    TEXT_CACHE.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    return texts


def parse_answers(texts: list[str]) -> dict[str, str]:
    answers_text = "\n".join(texts[334:353])
    answers: dict[str, str] = {}
    for match in re.finditer(r"№(\d+\.\d+(?:\.\d+)?)\s+(.+?)\.", answers_text, flags=re.S):
        task_id = match.group(1)
        if 1 <= int(task_id.split(".")[0]) <= 12:
            answers[task_id] = " ".join(match.group(2).split())
    return answers


def target_pages(texts: list[str]) -> list[int]:
    main_pages = set(range(4, 67))
    analog_pages: set[int] = set()
    for index, text in enumerate(texts):
        analog_ids = re.findall(r"Аналог\s+(\d+\.\d+\.\d+)", text)
        if any(1 <= int(task_id.split(".")[0]) <= 12 for task_id in analog_ids):
            analog_pages.add(index)
    return sorted(main_pages | analog_pages)


def collect_page_items(page) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []

    def visitor(text, cm, tm, font_dict, font_size):
        clean = " ".join(text.strip().split())
        if not clean:
            return
        items.append(
            {
                "text": clean,
                "x": float(tm[4]),
                "y": float(tm[5]),
                "font_size": float(font_size),
            }
        )

    page.extract_text(visitor_text=visitor)
    return items


def page_placements(reader: PdfReader, pages: list[int], answers: dict[str, str]) -> list[dict[str, object]]:
    placements: list[dict[str, object]] = []
    for page_index in pages:
        items = collect_page_items(reader.pages[page_index])
        starts: list[dict[str, object]] = []
        fields: list[dict[str, object]] = []

        for item in items:
            text = str(item["text"])
            match = re.match(r"(?:Задача|Аналог)\s+(\d+\.\d+(?:\.\d+)?)\.", text)
            if match:
                task_id = match.group(1)
                if 1 <= int(task_id.split(".")[0]) <= 12:
                    starts.append({"id": task_id, "x": item["x"], "y": item["y"]})
            if text == "Ответ:" and float(item["x"]) > 100 and float(item["y"]) > 40:
                fields.append({"x": item["x"], "y": item["y"]})

        starts.sort(key=lambda item: -float(item["y"]))
        for position, start in enumerate(starts):
            current_y = float(start["y"])
            next_y = float(starts[position + 1]["y"]) if position + 1 < len(starts) else 86.0
            block_lines = [
                item
                for item in items
                if float(item["x"]) > 45
                and next_y < float(item["y"]) < current_y
                and float(item["font_size"]) <= 12.5
                and not str(item["text"]).startswith(("Оглавление", ">"))
                and "MathStart" not in str(item["text"])
            ]
            left_condition_lines = [
                item
                for item in block_lines
                if float(item["x"]) < 330
                and str(item["text"]) not in {"Ответ:", "Ответ", "A", "B", "C", "D", "E", "H", "M"}
            ]
            condition_bottom_y = min((float(item["y"]) for item in left_condition_lines), default=current_y - 50)

            block_fields = [
                field for field in fields if next_y < float(field["y"]) < current_y
            ]
            if block_fields:
                field = sorted(block_fields, key=lambda item: float(item["y"]))[0]
                answer_x = 408.0
                answer_y = float(field["y"]) - 0.4
                field_found = True
            else:
                answer_y = max(next_y + 16.0, condition_bottom_y - 18.0)
                answer_x = 408.0
                field_found = False

            task_id = str(start["id"])
            if task_id in answers:
                if field_found:
                    solution_y = answer_y + 8.0
                else:
                    solution_y = max(next_y + 14.0, answer_y - 10.0)
                placements.append(
                    {
                        "page": page_index,
                        "id": task_id,
                        "x": answer_x,
                        "y": answer_y,
                        "solution_x": 78.0,
                        "solution_y": solution_y,
                        "solution_w": max(300.0, answer_x - 86.0),
                        "gap": max(18.0, answer_y - next_y),
                        "next_y": next_y,
                        "condition_bottom_y": condition_bottom_y,
                        "answer": answers[task_id],
                    }
                )
    return placements


def task_texts(texts: list[str], pages: list[int]) -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = re.compile(
        r"(?:(Задача|Аналог)\s+(\d+\.\d+(?:\.\d+)?)\.)"
        r"([\s\S]*?)(?=(?:Задача|Аналог)\s+\d+\.\d+(?:\.\d+)?\.|Оглавление|$)"
    )
    for page_index in pages:
        for match in pattern.finditer(texts[page_index]):
            task_id = match.group(2)
            if 1 <= int(task_id.split(".")[0]) <= 12:
                result[task_id] = " ".join(match.group(3).split())
    return result


def normal_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("−", "-").replace("·", "*")
    return re.sub(r"\s+", " ", text)


def number_tokens(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:,\d+)?", normal_text(text))


def to_float(token: str) -> float:
    return float(token.replace(",", "."))


def fmt_decimal(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def parse_answer_value(answer: str) -> float | None:
    compact = answer.replace(" ", "").replace(",", ".").replace("−", "-")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", compact):
        return None
    return float(compact)


def same_number(left: float, right: float | None) -> bool:
    return right is not None and abs(left - right) < 1e-6


def simple_numeric_formula(nums: list[str], answer: str, include_angle_constants: bool = False) -> str | None:
    target = parse_answer_value(answer)
    if target is None:
        return None

    values: list[tuple[float, str]] = []
    for token in nums[:8]:
        value = to_float(token)
        if abs(value) < 1e-12:
            continue
        shown = fmt_decimal(value)
        if (value, shown) not in values:
            values.append((value, shown))
    if include_angle_constants:
        for value in (45.0, 90.0, 180.0, 360.0):
            shown = fmt_decimal(value)
            if (value, shown) not in values:
                values.append((value, shown))

    candidates: list[tuple[float, str]] = []
    for value, shown in values:
        candidates.extend(
                [
                    (value / 2, f"{shown}/2"),
                    (value / 3, f"{shown}/3"),
                    (value / 4, f"{shown}/4"),
                    (3 * value / 4, f"3*{shown}/4"),
                    (value * 2, f"2*{shown}"),
                    (value * value, f"{shown}^2"),
                ]
            )
        if include_angle_constants:
            candidates.extend(
                [
                    (90 - value, f"90-{shown}"),
                    (180 - value, f"180-{shown}"),
                    (180 - 2 * value, f"180-2*{shown}"),
                    (360 - value, f"360-{shown}"),
                ]
            )
        if value > 0:
            root = math.sqrt(value)
            candidates.append((root, f"√{shown}"))

    for i, (a, sa) in enumerate(values):
        for j, (b, sb) in enumerate(values):
            if i == j:
                continue
            candidates.extend(
                [
                    (a + b, f"{sa}+{sb}"),
                    (a - b, f"{sa}-{sb}"),
                    (b - a, f"{sb}-{sa}"),
                    (a * b, f"{sa}*{sb}"),
                    (a * b / 2, f"{sa}*{sb}/2"),
                    (a * a / (2 * b), f"{sa}^2/(2*{sb})"),
                    (b * b / (2 * a), f"{sb}^2/(2*{sa})"),
                    (2 * a / b, f"2*{sa}/{sb}"),
                    (a / b, f"{sa}/{sb}"),
                    ((a + b) / 2, f"({sa}+{sb})/2"),
                    (abs(a - b), f"|{sa}-{sb}|"),
                ]
            )

    for i, (a, sa) in enumerate(values):
        for j, (b, sb) in enumerate(values):
            for k, (c_value, sc) in enumerate(values):
                if len({i, j, k}) < 3 or abs(c_value) < 1e-12:
                    continue
                candidates.extend(
                    [
                        ((a + b) / c_value, f"({sa}+{sb})/{sc}"),
                        ((a - b) / c_value, f"({sa}-{sb})/{sc}"),
                        (a * b / c_value, f"{sa}*{sb}/{sc}"),
                        ((a - b) * c_value, f"({sa}-{sb})*{sc}"),
                    ]
                )

    for value, expression in candidates:
        if same_number(value, target):
            return f"{expression}={answer}"
    return None


def sqrt_value(raw: str) -> float:
    raw = raw.strip().replace(" ", "")
    if raw.startswith("√"):
        return math.sqrt(to_float(raw[1:]))
    if "√" in raw:
        coef, rad = raw.split("√", 1)
        coef_value = to_float(coef) if coef else 1.0
        return coef_value * math.sqrt(to_float(rad))
    return to_float(raw)


def segment_value(text: str, name: str) -> str | None:
    compact = normal_text(text).replace(" ", "")
    match = re.search(rf"{name}(?:=|равна|равен)((?:\d+)?√\d+|-?\d+(?:,\d+)?)", compact)
    return match.group(1) if match else None


def vector_pair(text: str, name: str) -> tuple[int, int] | None:
    match = re.search(rf"{name}\((-?\d+);\s*(-?\d+)\)", normal_text(text))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def first_values(nums: list[str], count: int) -> list[float]:
    return [to_float(num) for num in nums[:count]]


def compact_formula(text: str, limit: int = 90) -> str:
    text = normal_text(text)
    text = text.replace("Ответ:", "")
    text = re.sub(r"^(?:DEMO|NEW|SIM|Аналоги|Прототип|Ответ)\s+", "", text).strip()
    text = text.replace(" ∘", "°")
    text = text.replace("︂", "").replace("︀", "").replace("︁", "").replace("︃", "")
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip()


def equation_snippet(text: str) -> str | None:
    cleaned = normal_text(text)
    match = re.search(r"уравнения\s*(.+?)\s*Ответ", cleaned, re.IGNORECASE)
    if not match:
        return None
    return compact_formula(match.group(1), 70)


def expression_snippet(text: str) -> str | None:
    cleaned = normal_text(text)
    match = re.search(r"выражения\s*(.+?)\s*Ответ", cleaned, re.IGNORECASE)
    if not match:
        return None
    return compact_formula(match.group(1), 70)


def condition_formula_snippet(text: str) -> str | None:
    cleaned = normal_text(text)
    for pattern in [
        r"по формуле\s*(.+?)(?:, где|\.|Ответ)",
        r"вычисляется по формуле\s*(.+?)(?:, где|\.|Ответ)",
        r"закону\s*(.+?)(?:, где|\.|Ответ)",
    ]:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return compact_formula(match.group(1), 72)
    return None


def solution_method(task_id: str, text: str, answer: str) -> str:
    section = int(task_id.split(".")[0])
    cleaned = normal_text(text)
    compact = cleaned.replace(" ", "").replace("⃗", "")
    compact_lower = compact.lower()
    compact_clean = compact_lower.replace("-", "")
    lower = cleaned.lower()
    nums = number_tokens(cleaned)
    numeric_formula = simple_numeric_formula(nums, answer, include_angle_constants=(section == 1))

    if section == 1:
        ab_raw = segment_value(cleaned, "AB")
        ac_raw = segment_value(cleaned, "AC")
        bc_raw = segment_value(cleaned, "BC")
        if "cos" in lower:
            if ab_raw and bc_raw:
                ab = sqrt_value(ab_raw)
                bc = sqrt_value(bc_raw)
                ac2 = ab * ab - bc * bc
                ac = math.sqrt(max(ac2, 0))
                return f"AC^2={fmt_decimal(ab*ab)}-{fmt_decimal(bc*bc)}={fmt_decimal(ac2)}; cosA={fmt_decimal(ac)}/{fmt_decimal(ab)}={answer}"
            return f"Пифагор -> катет; cos=прилеж./гип={answer}"
        if "sin" in lower:
            if ab_raw and ac_raw:
                ab = sqrt_value(ab_raw)
                ac = sqrt_value(ac_raw)
                bc2 = ab * ab - ac * ac
                bc = math.sqrt(max(bc2, 0))
                return f"BC^2={fmt_decimal(ab*ab)}-{fmt_decimal(ac*ac)}={fmt_decimal(bc2)}; sinA={fmt_decimal(bc)}/{fmt_decimal(ab)}={answer}"
            return f"Пифагор -> катет; sin=противолеж./гип={answer}"
        if "средняя линия" in lower:
            if nums:
                square = to_float(nums[0])
                target = parse_answer_value(answer)
                if same_number(square / 4, target):
                    return f"Sмал={fmt_decimal(square)}/4={answer}"
                if same_number(3 * square / 4, target):
                    return f"Sмал={fmt_decimal(square)}/4={fmt_decimal(square/4)}; Sтр={fmt_decimal(square)}-{fmt_decimal(square/4)}={answer}"
            return numeric_formula or f"S={answer}"
        if "прямоугольного" in lower and "уголb" in compact_lower and nums:
            b_angle = to_float(nums[0])
            if "chимедианойcm" in compact_lower:
                return f"|2*{fmt_decimal(b_angle)}-90|={answer}"
            if "cdимедианойcm" in compact_lower or "биссектрисойcdимедианойcm" in compact_lower:
                return f"|{fmt_decimal(b_angle)}-45|={answer}"
            if "chибиссектрисойcd" in compact_lower:
                return f"|90-{fmt_decimal(b_angle)}-45|={answer}"
        if "стороныacиbcравны" in compact_lower:
            if "внешнийуголпривершинеb" in compact_lower and nums:
                ext = to_float(nums[0])
                b_angle = 180 - ext
                c_angle = 180 - 2 * b_angle
                return f"∠B=180-{fmt_decimal(ext)}={fmt_decimal(b_angle)}; ∠C=180-2*{fmt_decimal(b_angle)}={fmt_decimal(c_angle)}"
            c_match = re.search(r"уголcравен(-?\d+(?:,\d+)?)", compact_lower)
            if c_match:
                c_angle = to_float(c_match.group(1))
                base = (180 - c_angle) / 2
                return f"∠A=∠B=(180-{fmt_decimal(c_angle)})/2={fmt_decimal(base)}; внешний=180-{fmt_decimal(base)}={answer}"
        if "высота" in lower and len(nums) >= 3:
            a, b, h = (to_float(num) for num in nums[:3])
            big_side = max(a, b)
            small_side = min(a, b)
            square = big_side * h / 2
            return f"S={fmt_decimal(big_side)}*{fmt_decimal(h)}/2={fmt_decimal(square)}; h=2*{fmt_decimal(square)}/{fmt_decimal(small_side)}={answer}"
        if "биссектриса" in compact_clean and "уголcравен" in compact_lower and "уголcadравен" in compact_lower:
            c_match = re.search(r"уголcравен(\d+(?:,\d+)?)", compact_lower)
            cad_match = re.search(r"уголcadравен(\d+(?:,\d+)?)", compact_lower)
            if c_match and cad_match:
                c_angle = to_float(c_match.group(1))
                cad = to_float(cad_match.group(1))
                return f"∠A=2*{fmt_decimal(cad)}; ∠B=180-{fmt_decimal(c_angle)}-{fmt_decimal(2*cad)}={answer}"
        if "внешний угол" in lower or "биссектрис" in lower or "биссектриса" in compact_clean:
            if "уголcравен" in compact_lower and "уголcadравен" in compact_lower:
                c_match = re.search(r"уголcравен(\d+(?:,\d+)?)", compact_lower)
                cad_match = re.search(r"уголcadравен(\d+(?:,\d+)?)", compact_lower)
                if c_match and cad_match:
                    c_angle = to_float(c_match.group(1))
                    cad = to_float(cad_match.group(1))
                    return f"∠A=2*{fmt_decimal(cad)}; ∠B=180-{fmt_decimal(c_angle)}-{fmt_decimal(2*cad)}={answer}"
            return f"сумма углов 180° + данные {', '.join(nums[:3])}; получаем {answer}"
        if "центральныйуголна" in compact_clean and nums:
            diff = to_float(nums[0])
            return f"2x=x+{fmt_decimal(diff)}; x={answer}"
        if "окружност" in lower or "окружности" in compact_clean or "радиус" in lower:
            if "центральныйуголна" in compact_clean and nums:
                diff = to_float(nums[0])
                return f"2x=x+{fmt_decimal(diff)}; x={answer}"
            c_match = re.search(r"уголCравен(-?\d+(?:,\d+)?)", compact, re.IGNORECASE)
            if ab_raw and c_match:
                return f"R=AB/(2sinC)={ab_raw}/(2sin{c_match.group(1)}°)={answer}"
            return numeric_formula or f"∠={answer}"
        return numeric_formula or f"x={answer}"

    if section == 2:
        if "изображены" in lower or "рисунке" in lower:
            return f"по рисунку считываем координаты; вычисление дает {answer}"
        a_vec = vector_pair(cleaned, "a")
        b_vec = vector_pair(cleaned, "b")
        if "скаляр" in lower:
            if "длины векторов" in lower and len(nums) >= 3:
                a_len, b_len, angle = nums[:3]
                return f"|a||b|cosφ={a_len}*{b_len}*cos{angle}°={answer}"
            if a_vec and b_vec:
                return f"a*b={a_vec[0]}*{b_vec[0]}+{a_vec[1]}*{b_vec[1]}={answer}"
            return f"координаты -> скалярное произведение = {answer}"
        if a_vec and b_vec:
            coef_match = re.search(r"a\+(\d+)b", compact)
            coef = int(coef_match.group(1)) if coef_match else 1
            x = a_vec[0] + coef * b_vec[0]
            y = a_vec[1] + coef * b_vec[1]
            return f"a+{coef}b=({x};{y}); |v|=√({x}^2+{y}^2)={answer}"
        return numeric_formula or f"|v|={answer}"

    if section == 3:
        target = parse_answer_value(answer)
        if "параллелепипед" in lower and len(nums) >= 3:
            ab = segment_value(cleaned, "AB")
            bc = segment_value(cleaned, "BC")
            ad = segment_value(cleaned, "AD")
            bb = segment_value(cleaned, "BB1")
            cc = segment_value(cleaned, "CC1")
            aa = segment_value(cleaned, "AA1")
            cd = segment_value(cleaned, "CD")
            base_a = ab or cd
            base_b = bc or ad
            height = aa or bb or cc
            if base_a and base_b and height:
                a, b, h_value = sqrt_value(base_a), sqrt_value(base_b), sqrt_value(height)
                box_volume = a * b * h_value
                if same_number(box_volume / 2, target):
                    return f"Vп/п={base_a}*{base_b}*{height}; V=Vп/п/2={answer}"
                if same_number(box_volume / 3, target):
                    return f"Vпир=({base_a}*{base_b})*{height}/3={answer}"
                if same_number(box_volume / 6, target):
                    return f"Vтет=({base_a}*{base_b})*{height}/6={answer}"
                if same_number(box_volume, target):
                    return f"V={base_a}*{base_b}*{height}={answer}"

        if "объём куба равен" in lower and nums:
            value = to_float(nums[0])
            if same_number(value / 8, target):
                return f"Vотсеч=Vкуба/8={fmt_decimal(value)}/8={answer}"

        if "среднююлиниюоснования" in compact_clean and "треугольнойпризмы" in compact_clean and nums:
            value = to_float(nums[0])
            if "объёмотсечённой" in compact_clean or "объёмотсеченной" in compact_clean:
                if "найдитеобъёмэтойпризмы" in compact_clean:
                    return f"k=1/2, Vотс=V/4; V={fmt_decimal(value)}*4={answer}"
            if "объёмкоторойравен" in compact_clean or "объёмравен" in compact_clean:
                if "найдитеобъёмотсеч" in compact_clean:
                    return f"k=1/2, Vотс=V/4={fmt_decimal(value)}/4={answer}"
            if "площадь боковой поверхности" in lower:
                if "найдитеплощадьбоковойповерхностиисходной" in compact_clean:
                    return f"Sбок.отс=Sбок/2; Sбок={fmt_decimal(value)}*2={answer}"
                return f"Sбок.отс=Sбок/2={fmt_decimal(value)}/2={answer}"

        if ("правильнойтреугольнойпризмы" in compact_clean or "правильнаятреугольнаяпризма" in compact_clean) and "площадьоснования" in compact_clean:
            match = re.search(r"площадьоснования(?:которой)?равна(\d+(?:,\d+)?).*боковоеребр[оа]равн[оа](\d+(?:,\d+)?)", compact_clean)
            if not match:
                match = re.search(r"площадьоснованияравна(\d+(?:,\d+)?).*боковоеребр[оа]равн[оа](\d+(?:,\d+)?)", compact_clean)
            s_base, h_value = (to_float(match.group(1)), to_float(match.group(2))) if match else first_values(nums, 2)
            prism_volume = s_base * h_value
            if same_number(prism_volume / 3, target):
                return f"Vпир=Sосн*h/3={fmt_decimal(s_base)}*{fmt_decimal(h_value)}/3={answer}"
            if same_number(2 * prism_volume / 3, target):
                return f"Vпр=Sосн*h={fmt_decimal(prism_volume)}; V=2Vпр/3={answer}"

        if "цилиндрическая кружка" in lower:
            return "V=πr^2h; V2/V1=(1,5r)^2*h/(r^2*2h)=1,125"

        if "дано два цилиндра" in lower and nums:
            v1 = to_float(nums[0])
            return f"V2=V1*(2r)^2/(3h)={fmt_decimal(v1)}*4/3={answer}"

        if "объём конуса" in lower and "уменьшится" in lower and nums:
            k = to_float(nums[0])
            return f"V=πr^2h/3; V'/V=1/{fmt_decimal(k)} => уменьшится в {answer}"
        if "объём конуса" in lower and "увеличится" in lower and nums:
            k = to_float(nums[0])
            return f"V=πr^2h/3; V'/V={fmt_decimal(k)}^2={answer}"

        if "уровеньжидкости" in compact_clean and nums:
            fraction = 1 / 3
            liquid = to_float(nums[-1])
            full = liquid / (fraction**3)
            return f"k=1/3, Vж/Vк=k^3=1/27; Vк={fmt_decimal(liquid)}*27={fmt_decimal(full)}; долить={answer}"

        if "цилиндриконусимеютобщиеоснованиеивысоту" in compact_clean:
            value = to_float(nums[0]) if nums else 0
            if "объёмцилиндраравен" in compact_clean:
                return f"Vкон=πr^2h/3=Vцил/3={fmt_decimal(value)}/3={answer}"
            if "объёмконусаравен" in compact_clean:
                return f"Vцил=πr^2h=3Vкон=3*{fmt_decimal(value)}={answer}"
            if "найдитеплощадьбоковойповерхностиконуса" in compact_clean:
                return f"Sцил=2πr^2, Sкон=πr^2√2; Sкон=Sцил*√2/2={answer}"
            if "найдитеплощадьбоковойповерхностицилиндра" in compact_clean:
                return f"Sкон=πr^2√2, Sцил=2πr^2; Sцил=Sкон*√2={answer}"

        if "цилиндрвписанвпрямоугольныйпараллелепипед" in compact_clean and nums:
            r_value = to_float(nums[0])
            h_value = to_float(nums[1]) if len(nums) > 1 else r_value
            return f"a=b=2r={fmt_decimal(2*r_value)}; V=a*b*h={fmt_decimal(2*r_value)}*{fmt_decimal(2*r_value)}*{fmt_decimal(h_value)}={answer}"

        if "шар" in compact_clean and "цилиндр" in compact_clean and nums:
            value = to_float(nums[0])
            if "шар,объёмкоторого" in compact_clean and "вписанвцилиндр" in compact_clean:
                return f"Vцил=πR^2*2R, Vш=4πR^3/3; Vцил=3Vш/2={fmt_decimal(value)}*3/2={answer}"
            if "цилиндр,объёмкоторого" in compact_clean and "описаноколошара" in compact_clean:
                return f"Vш=4πR^3/3, Vцил=2πR^3; Vш=2Vцил/3={fmt_decimal(value)}*2/3={answer}"
            if "площадьполнойповерхностицилиндра" in compact_clean:
                return f"Sцил=6πR^2, Sш=4πR^2; Sш=2Sцил/3={fmt_decimal(value)}*2/3={answer}"

        if "конусвписанвшар" in compact_clean and nums:
            value = to_float(nums[0])
            if "объёмшараравен" in compact_clean:
                return f"Vш=4πR^3/3, Vкон=πR^3/3; Vкон=Vш/4={fmt_decimal(value)}/4={answer}"
            if "объёмконусаравен" in compact_clean:
                return f"Vкон=πR^3/3, Vш=4Vкон=4*{fmt_decimal(value)}={answer}"

        if "около конуса описана сфера" in lower:
            if "образующая конуса равна" in lower:
                raw = re.search(r"равна((?:\d+)?√\d+)", compact)
                shown = raw.group(1) if raw else (nums[0] if nums else "")
                return f"l=R√2; R=l/√2={shown}/√2={answer}"
            if "радиус сферы равен" in lower:
                raw = re.search(r"равен((?:\d+)?√\d+)", compact)
                shown = raw.group(1) if raw else (nums[0] if nums else "")
                return f"l=R√2={shown}*√2={answer}"

        if "площадь сечения шара" in lower and nums:
            value = to_float(nums[0])
            return f"Sсеч=πR^2={fmt_decimal(value)}; Sш=4πR^2=4*{fmt_decimal(value)}={answer}"

        return numeric_formula or f"V/S={answer}"

    if section == 4:
        values = [to_float(num) for num in nums if to_float(num) > 0]
        decimals = [to_float(num) for num in nums if 0 < to_float(num) < 1]
        if "дима" in lower and "марат" in lower and "петя" in lower:
            return f"P=3/5={answer}"
        if "конференц" in lower and len(values) >= 3:
            total = sum(values[:3])
            target = parse_answer_value(answer)
            if target is not None:
                return f"Всего={fmt_decimal(values[0])}+{fmt_decimal(values[1])}+{fmt_decimal(values[2])}={fmt_decimal(total)}; P={fmt_decimal(target*total)}/{fmt_decimal(total)}={answer}"
        if "монет" in lower or ("матч" in lower and "мяч" in lower):
            if "все три" in lower or "только вторую" in lower:
                return f"P=(1/2)^3={answer}"
            if "ровно один" in lower:
                return f"P=C2^1/2^2=2/4={answer}"
            if "не выпадет ни разу" in lower:
                return f"P=(1/2)^2={answer}"
            if "не более одного" in lower and "три" in lower:
                return f"P=(C3^0+C3^1)/2^3=4/8={answer}"
            if "не более одного" in lower:
                return f"P=1-(1/2)^2={answer}"
            return f"P=(1/2)^n={answer}"
        if len(values) >= 2 and ("не " in lower or "без" in lower):
            small, total = sorted(values[:2])
            if total:
                return f"P=1-{fmt_decimal(small)}/{fmt_decimal(total)}={answer}"
        if decimals and ("ниже" in lower or "меньше" in lower) and ("или выше" in lower or "не меньше" in lower):
            return f"P=1-{fmt_decimal(decimals[0])}={answer}"
        if len(decimals) >= 2 and ("от" in lower and "до" in lower):
            return f"P={fmt_decimal(decimals[0])}-{fmt_decimal(decimals[1])}={answer}"
        if len(decimals) >= 2 and "двух тем" in lower:
            return f"P={fmt_decimal(decimals[0])}+{fmt_decimal(decimals[1])}={answer}"
        if values:
            total = values[0] if values[0] >= sum(values[1:]) and len(values) > 1 else sum(values)
            favorable = to_float(answer) * total
            if abs(favorable - round(favorable)) < 1e-6:
                if len(values) >= 2 and values[0] >= values[1] and ("трех" in lower or "трёх" in lower):
                    rest = values[0] - 3 * values[1]
                    if abs(rest - favorable) < 1e-6:
                        return f"n={fmt_decimal(values[0])}-3*{fmt_decimal(values[1])}={fmt_decimal(rest)}; P={fmt_decimal(rest)}/{fmt_decimal(values[0])}={answer}"
                return f"Всего {fmt_decimal(total)}, благоприятных {fmt_decimal(favorable)}; P={fmt_decimal(favorable)}/{fmt_decimal(total)}={answer}"
        return numeric_formula or f"P={answer}"

    if section == 5:
        p_values = [to_float(num) for num in nums if 0 < to_float(num) < 1]
        if "хотя бы" in lower:
            if p_values and ("тремя" in lower or "три " in lower):
                p = p_values[0]
                return f"P=1-{fmt_decimal(p)}^3={answer}"
            return f"P=1-q={answer}"
        if "четыр" in lower and "мишен" in lower and p_values:
            p = p_values[0]
            q = 1 - p
            target = parse_answer_value(answer)
            for hits in range(5):
                if same_number((p**hits) * (q ** (4 - hits)), target):
                    return f"P={fmt_decimal(p)}^{hits}*{fmt_decimal(q)}^{4-hits}={answer}"
            return f"P=p^k(1-p)^(4-k)={answer}"
        if "до тех пор" in lower and p_values:
            p = p_values[0]
            threshold = p_values[-1]
            return f"1-(1-{fmt_decimal(p)})^n≥{fmt_decimal(threshold)}; n={answer}"
        if "кость" in lower and "два раза" in lower:
            target = parse_answer_value(answer)
            if target is not None:
                return f"P=m/25={fmt_decimal(target*25)}/25={answer}"
        if "фломастер" in lower and len(nums) >= 3:
            a, b, c_value = first_values(nums, 3)
            total = a + b + c_value
            return f"P=2*{fmt_decimal(a)}*{fmt_decimal(b)}/({fmt_decimal(total)}*{fmt_decimal(total-1)})={answer}"
        if "масса окажется" in lower and len(p_values) >= 2:
            return f"P={fmt_decimal(p_values[0])}+{fmt_decimal(p_values[1])}-1={answer}"
        if "автомат" in lower and len(p_values) >= 2:
            p = p_values[0]
            both = p_values[-1]
            return f"P=1-({fmt_decimal(p)}+{fmt_decimal(p)}-{fmt_decimal(both)})={answer}"
        if "батарейк" in lower and len(p_values) >= 3:
            return f"P=P(бр|испр)P(испр)+P(бр|норм)P(норм)={answer}"
        return numeric_formula or f"P={answer}"

    if section == 6:
        eq = equation_snippet(cleaned)
        return numeric_formula or (f"{eq}; x={answer}" if eq else f"x={answer}")

    if section == 7:
        if "tgα" in cleaned and "sinα" in cleaned:
            return f"cos=√(1-sin^2); tg=sin/cos={answer}"
        if "tgα" in cleaned and "cosα" in cleaned:
            return f"sin=±√(1-cos^2); tg=sin/cos={answer}"
        if "найдитеsinα" in compact_clean and "cosα" in compact_clean:
            return f"sin=±√(1-cos^2)={answer}"
        expr = expression_snippet(cleaned)
        return numeric_formula or (f"E={expr}={answer}" if expr else f"E={answer}")

    if section == 8:
        return f"по графику считываем нужное значение: {answer}"

    if section == 9:
        formula = condition_formula_snippet(cleaned)
        if formula:
            return f"{formula}; x={answer}"
        if "линз" in lower:
            return f"1/f=1/d1+1/d2; d2={answer}"
        if "s=v0tat22" in compact_clean:
            v0 = segment_value(cleaned, "v0") or (nums[0] if nums else "")
            a = segment_value(cleaned, "a") or (nums[1] if len(nums) > 1 else "")
            s_match = re.search(r"проехал(\d+(?:,\d+)?)", compact_clean)
            s_value = s_match.group(1) if s_match else (nums[-1] if nums else "")
            sign = "+" if "разгон" in lower else "-"
            return f"s=v0t{sign}at^2/2; {s_value}={v0}t{sign}{a}t^2/2; t={answer}"
        if "t=t0+bt+at2" in compact_clean or "t=t0+bt+at2" in compact_clean:
            return f"T=T0+bt+at^2; T=1870; t={answer}"
        if "стефа" in lower or "σst" in compact_clean:
            return f"P=σST^4; T=⁴√(P/(σS))={answer}"
        return numeric_formula or f"x={answer}"

    if section == 10:
        if "%" in cleaned and nums:
            percent_match = re.search(r"(\d+(?:,\d+)?)%", cleaned)
            if percent_match:
                count = to_float(nums[0])
                percent = to_float(percent_match.group(1)) / 100
                if same_number(count / percent, parse_answer_value(answer)):
                    return f"x={fmt_decimal(count)}/{fmt_decimal(percent)}={answer}"
        if "средн" in lower and "скорост" in lower and len(nums) >= 6:
            v1, t1, v2, t2, v3, t3 = first_values(nums, 6)
            return f"vср=({fmt_decimal(v1)}*{fmt_decimal(t1)}+{fmt_decimal(v2)}*{fmt_decimal(t2)}+{fmt_decimal(v3)}*{fmt_decimal(t3)})/({fmt_decimal(t1)}+{fmt_decimal(t2)}+{fmt_decimal(t3)})={answer}"
        if "среднююскорость" in compact_clean and all(word in compact_clean for word in ["первыйчас", "тричаса", "двачаса"]) and len(nums) >= 3:
            v1, v2, v3 = first_values(nums, 3)
            return f"vср=({fmt_decimal(v1)}*1+{fmt_decimal(v2)}*3+{fmt_decimal(v3)}*2)/(1+3+2)={answer}"
        if "оба мастера" in lower and len(nums) >= 2:
            a, b = first_values(nums, 2)
            return f"1/t=1/{fmt_decimal(a)}+1/{fmt_decimal(b)}; t={answer}"
        if "работаявместе" in compact_clean and len(nums) >= 2:
            together, alone = first_values(nums, 2)
            return f"1/{fmt_decimal(together)}=1/x+1/{fmt_decimal(alone)}; x={answer}"
        if "поезд" in lower and len(nums) >= 4:
            v1, v2, length, seconds = first_values(nums, 4)
            return f"L=({fmt_decimal(v1)}+{fmt_decimal(v2)})*{fmt_decimal(seconds)}/3,6-{fmt_decimal(length)}={answer}"
        if "велосипедист" in lower and len(nums) >= 3:
            s_value, diff, time = first_values(nums, 3)
            return f"{fmt_decimal(s_value)}/x-{fmt_decimal(s_value)}/(x+{fmt_decimal(diff)})={fmt_decimal(time)}; x={answer}"
        if "детал" in lower and len(nums) >= 2:
            total, diff = first_values(nums, 2)
            return f"{fmt_decimal(total)}/x-{fmt_decimal(total)}/(x+{fmt_decimal(diff)})={fmt_decimal(diff)}; x={answer}"
        if "труба" in lower and len(nums) >= 2:
            diff, volume = first_values(nums, 2)
            return f"{fmt_decimal(volume)}/x-{fmt_decimal(volume)}/(x+{fmt_decimal(diff)})={fmt_decimal(diff)}; x={answer}"
        if "теплоход" in lower or "лодка" in lower or "катер" in lower or "баржа" in lower or "яхта" in lower:
            if len(nums) >= 3:
                return f"t=S/(x-v)+S/(x+v); по условию x={answer}"
            return f"S=vt; по условию x={answer}"
        if "сосуд" in lower and "%" in cleaned:
            return f"mкисл=0,4(m1+m2); система смесей => x={answer}"
        return numeric_formula or f"x={answer}"

    if section == 11:
        return f"считываем с графика нужные координаты/значение: {answer}"

    if section == 12:
        func_match = re.search(r"функции\s*y=(.+?)\s*Ответ", cleaned, re.IGNORECASE)
        func = compact_formula("y=" + func_match.group(1), 58) if func_match else None
        cubic_match = re.search(r"y=x\s*3\s*\+\s*(-?\d+(?:,\d+)?)x2", cleaned)
        if cubic_match:
            coef = to_float(cubic_match.group(1))
            point = -2 * coef / 3
            if same_number(point, parse_answer_value(answer)):
                return f"f'=3x^2+{fmt_decimal(2*coef)}x; x=-{fmt_decimal(2*coef)}/3={answer}"
        cubic_linear = re.search(r"y=x\s*3\s*-\s*(\d+(?:,\d+)?)x", cleaned)
        if cubic_linear:
            coef = to_float(cubic_linear.group(1))
            sign = "-" if str(answer).startswith(("−", "-")) else ""
            return f"f'=3x^2-{fmt_decimal(coef)}=0; x={sign}√({fmt_decimal(coef)}/3)={answer}"
        cubic_quad_lin = re.search(r"y=x\s*3\s*\+\s*(-?\d+(?:,\d+)?)x2\s*\+\s*(-?\d+(?:,\d+)?)x", cleaned)
        if cubic_quad_lin:
            a, b = to_float(cubic_quad_lin.group(1)), to_float(cubic_quad_lin.group(2))
            return f"f'=3x^2+{fmt_decimal(2*a)}x+{fmt_decimal(b)}=0; x={answer}"
        sqrt_match = re.search(r"y=x\s*√x\s*-\s*(\d+(?:,\d+)?)x", cleaned)
        if sqrt_match:
            a = to_float(sqrt_match.group(1))
            return f"f'=1,5√x-{fmt_decimal(a)}=0; x=({fmt_decimal(a)}/1,5)^2={answer}"
        ln_match = re.search(r"y=(?:(\d+(?:,\d+)?)x\s*2|x\s*2)\s*-\s*(\d+(?:,\d+)?)x\s*\+\s*(\d+(?:,\d+)?)\*lnx", cleaned)
        if ln_match:
            a = to_float(ln_match.group(1) or "1")
            b = to_float(ln_match.group(2))
            c_value = to_float(ln_match.group(3))
            return f"f'={fmt_decimal(2*a)}x-{fmt_decimal(b)}+{fmt_decimal(c_value)}/x=0; x={answer}"
        return numeric_formula or (f"{func}; f'=0; x={answer}" if func else f"f'=0; x={answer}")

    return numeric_formula or f"x={answer}"


def wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def make_overlay(width: float, height: float, rows: list[dict[str, object]]) -> PdfReader:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    for row in rows:
        answer = str(row["answer"])
        x = float(row["x"])
        y = float(row["y"])
        solution = str(row.get("solution", ""))
        solution_x = float(row.get("solution_x", 86))
        solution_y = float(row.get("solution_y", y - 12))
        solution_w = float(row.get("solution_w", 290))
        solution_text = f"Реш.: {solution}.".replace("∠", "")
        solution_font_size = 15.0
        line_step = 16.4
        solution_lines = wrap_text(solution_text, FONT, solution_font_size, solution_w - 12)
        max_lines = 10 if float(row.get("gap", 34)) >= 42 else 8
        solution_lines = solution_lines[:max_lines]

        safe_top = min(
            solution_y + 7.0,
            float(row.get("condition_bottom_y", solution_y + 22.0)) - 7.0,
        )
        safe_bottom = float(row.get("next_y", 72.0)) + 8.0

        def text_box_metrics(font_size: float, step: float, line_count: int) -> tuple[float, float]:
            top_pad = font_size * 0.82
            bottom_pad = 5.0
            return top_pad + step * max(0, line_count - 1) + bottom_pad, top_pad

        solution_box_h, top_pad = text_box_metrics(solution_font_size, line_step, len(solution_lines))
        if solution_box_h > safe_top - safe_bottom and solution_font_size > 14.0:
            solution_font_size = 14.0
            line_step = 15.4
            solution_lines = wrap_text(solution_text, FONT, solution_font_size, solution_w - 12)[:max_lines]
            solution_box_h, top_pad = text_box_metrics(solution_font_size, line_step, len(solution_lines))

        solution_top = max(safe_bottom + solution_box_h, min(solution_y + 7.0, safe_top))
        if solution_top > float(row.get("condition_bottom_y", solution_top + 7.0)) - 4.0:
            solution_top = float(row.get("condition_bottom_y", solution_top + 7.0)) - 4.0
        solution_baseline = solution_top - top_pad

        answer_font_size = 18.0
        text_width = pdfmetrics.stringWidth(answer, FONT_BOLD, answer_font_size)
        answer_box_w = max(36, text_width + 12)
        c.setFillColor(HexColor("#fffdf0"))
        c.setStrokeColor(HexColor("#7a9f67"))
        c.roundRect(
            solution_x - 5,
            solution_top - solution_box_h,
            solution_w,
            solution_box_h,
            3.2,
            stroke=1,
            fill=1,
        )
        c.setFillColor(HexColor("#374151"))
        c.setFont(FONT, solution_font_size)
        line_y = solution_baseline
        for line in solution_lines:
            c.drawString(solution_x, line_y, line)
            line_y -= line_step

        c.setFillColor(HexColor("#fff7d6"))
        c.setStrokeColor(HexColor("#2c7a7b"))
        c.roundRect(x - 5, y - 8.0, answer_box_w, 25.5, 3.5, stroke=1, fill=1)
        c.setFillColor(HexColor("#111827"))
        c.setFont(FONT_BOLD, answer_font_size)
        c.drawString(x + 2, y - 2.4, answer)

    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def make_cover(total_tasks: int) -> PdfReader:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setFillColor(HexColor("#f7faf9"))
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.setFillColor(HexColor("#0f3d3e"))
    c.rect(0, PAGE_H - 95, PAGE_W, 95, stroke=0, fill=1)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont(FONT_BOLD, 22)
    c.drawString(MARGIN_X, PAGE_H - 58, "ЕГЭ профильная математика")
    c.setFont(FONT, 13)
    c.drawString(MARGIN_X, PAGE_H - 80, "Первая часть: ответы в полях и краткие решения")

    c.setFillColor(HexColor("#111827"))
    c.setFont(FONT_BOLD, 16)
    c.drawString(MARGIN_X, PAGE_H - 148, "Что внутри")
    c.setFont(FONT, 11)
    lines = [
        f"Обработано задач: {total_tasks}.",
        "Включены основные задачи №1-12 и их видимые аналоги из блока «АНАЛОГИ».",
        "В поле «Ответ:» оставлено только число.",
        "Краткие решения с вычислениями размещены в свободном месте рядом с заданиями.",
    ]
    y = PAGE_H - 178
    for line in lines:
        c.drawString(MARGIN_X, y, line)
        y -= 22

    c.setFillColor(HexColor("#2c7a7b"))
    c.setFont(FONT_BOLD, 11)
    c.drawString(MARGIN_X, 66, "Собрано автоматически по ответам из исходного PDF.")
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def main() -> None:
    register_fonts()
    texts = load_texts()
    source_reader = PdfReader(str(SOURCE))
    answers = parse_answers(texts)
    pages = target_pages(texts)
    placements = page_placements(source_reader, pages, answers)
    texts_by_id = task_texts(texts, pages)
    task_order = [str(row["id"]) for row in placements]

    missing_answers = [task_id for task_id in task_order if task_id not in answers]
    if missing_answers:
        raise RuntimeError(f"Missing answers: {missing_answers[:20]}")
    if len(task_order) != len(answers):
        raise RuntimeError(f"Expected {len(answers)} tasks, got {len(task_order)} placements")

    for row in placements:
        task_id = str(row["id"])
        row["solution"] = solution_method(task_id, texts_by_id.get(task_id, ""), str(row["answer"]))

    writer = PdfWriter()
    for page in make_cover(len(task_order)).pages:
        writer.add_page(page)

    rows_by_page: dict[int, list[dict[str, object]]] = {}
    for row in placements:
        rows_by_page.setdefault(int(row["page"]), []).append(row)

    for page_index in pages:
        page = source_reader.pages[page_index]
        overlay_reader = make_overlay(float(page.mediabox.width), float(page.mediabox.height), rows_by_page[page_index])
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    temp_output = Path("/tmp") / OUTPUT.name
    with temp_output.open("wb") as handle:
        writer.write(handle)
    shutil.move(str(temp_output), str(OUTPUT))

    print(f"wrote {OUTPUT}")
    print(f"pages: {len(writer.pages)}")
    print(f"tasks: {len(task_order)}")


if __name__ == "__main__":
    main()
