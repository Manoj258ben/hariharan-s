"""
Ruralkirana natural language processing & voice parsing service.
Handles Hinglish, Hindi, and English voice transcriptions and notebook OCR lines.
Maps spoken phrases like:
'Aaj das biscuit packet bike aur paanch litre tel aaya'
into structured transaction drafts with product matching, quantity, and transaction type.
"""
import re
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from ..models import Product

# Hindi/Hinglish & English Number Words Mapping
NUMBER_WORDS = {
    "ek": 1, "aik": 1, "one": 1,
    "do": 2, "two": 2,
    "teen": 3, "tin": 3, "three": 3,
    "char": 4, "chaar": 4, "four": 4,
    "paanch": 5, "panch": 5, "five": 5,
    "chhe": 6, "che": 6, "six": 6,
    "saat": 7, "seven": 7,
    "aath": 8, "ath": 8, "eight": 8,
    "nau": 9, "nine": 9,
    "das": 10, "ten": 10,
    "gyarah": 11, "eleven": 11,
    "barah": 12, "twelve": 12,
    "terah": 13, "thirteen": 13,
    "chaudah": 14, "fourteen": 14,
    "pandrah": 15, "fifteen": 15,
    "solah": 16, "sixteen": 16,
    "satrah": 17, "seventeen": 17,
    "atharah": 18, "eighteen": 18,
    "unnis": 19, "nineteen": 19,
    "bees": 20, "twenty": 20,
    "pachees": 25, "twentyfive": 25,
    "tees": 30, "thirty": 30,
    "chalis": 40, "forty": 40,
    "pachaas": 50, "pachas": 50, "fifty": 50,
    "sau": 100, "hundred": 100,
}

# Synonyms for Common Indian Kirana Products
SYNONYMS = {
    "biscuit": ["parle-g", "biscuit", "parle", "cookies"],
    "tel": ["cooking oil", "tel", "oil", "refined", "mustard oil", "sarson"],
    "oil": ["cooking oil", "tel", "oil"],
    "doodh": ["milk", "doodh", "amul", "dairy"],
    "milk": ["milk", "doodh"],
    "bread": ["bread", "loaf", "pao", "pav"],
    "anda": ["eggs", "egg", "ande", "anda"],
    "eggs": ["eggs", "egg", "ande"],
    "chai": ["tea", "chai", "patti", "tea leaves"],
    "tea": ["tea", "chai", "tea leaves"],
    "cheeni": ["sugar", "cheeni", "shakkar"],
    "sugar": ["sugar", "cheeni"],
    "atta": ["wheat flour", "atta", "flour"],
    "flour": ["wheat flour", "atta"],
    "sabun": ["bath soap", "soap", "sabun", "lifebuoy", "lux"],
    "soap": ["bath soap", "soap", "sabun"],
    "kela": ["banana", "kela", "kele"],
    "banana": ["banana", "kela"],
    "aloo": ["potato", "aloo", "batata"],
    "potato": ["potato", "aloo"],
    "maggi": ["maggi noodles", "maggi", "noodles"],
    "noodles": ["maggi noodles", "noodles"],
    "butter": ["almond butter", "butter", "makhan"],
    "makhan": ["butter", "almond butter"],
}

# Transaction type indicator keywords
SALE_KEYWORDS = {"bike", "bika", "biki", "becha", "bik", "sold", "sale", "nikla", "out"}
STOCK_IN_KEYWORDS = {"aaya", "aaye", "aayi", "aayege", "delivery", "delivered", "received", "in", "mila", "khareeda", "bought", "stock-in"}


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_best_matching_product(db: Session, text: str) -> Optional[Dict[str, Any]]:
    """
    Matches an extracted product mention against active products in SQLite.
    Returns matched Product info or None.
    """
    clean_text = text.lower().strip()
    products = db.query(Product).filter(Product.is_archived == False).all()
    if not products:
        return None

    best_match = None
    best_score = 0.0

    # 1. Direct or partial synonym match
    target_names = [clean_text]
    for key, syn_list in SYNONYMS.items():
        if key in clean_text or any(s in clean_text for s in syn_list):
            target_names.extend(syn_list)

    for p in products:
        p_name = p.product_name.lower()
        p_cat = p.category.lower()
        p_id = p.product_id.lower()

        # Check exact tokens
        for target in target_names:
            score = similarity(target, p_name)
            # Boost if category matches or words appear inside product name
            if target in p_name:
                score = max(score, 0.88)
            if target == p_id or clean_text == p_id:
                score = 1.0

            if score > best_score:
                best_score = score
                best_match = p

    if best_match and best_score >= 0.45:
        return {
            "product_id": best_match.product_id,
            "product_name": best_match.product_name,
            "category": best_match.category,
            "current_stock": best_match.current_stock,
            "selling_price": best_match.selling_price,
            "purchase_price": best_match.purchase_price,
            "unit": best_match.unit,
            "match_confidence": round(best_score * 100, 1),
            "is_confident": best_score >= 0.70,
        }
    return None


def parse_voice_transcript(db: Session, transcript: str) -> List[Dict[str, Any]]:
    """
    Parses complex spoken sentences like:
    'Aaj das biscuit packet bike aur paanch litre tel aaya'
    Splits by clauses or 'aur', 'and', commas, then identifies quantity, product, and action.
    """
    if not transcript or not transcript.strip():
        return []

    # Split into clauses by conjunctions
    clauses = re.split(r'\b(?:aur|and|tatha|va|phir|,)\b', transcript, flags=re.IGNORECASE)
    results = []

    for clause in clauses:
        clause_str = clause.strip()
        if not clause_str:
            continue

        words = clause_str.split()
        qty = None
        action = "SALE"  # Default assumption for daily kirana shop note

        # Detect action
        for w in words:
            w_lower = w.lower()
            if w_lower in STOCK_IN_KEYWORDS:
                action = "STOCK_IN"
            elif w_lower in SALE_KEYWORDS:
                action = "SALE"

        # Detect quantity (digits or number words)
        cleaned_words = []
        for w in words:
            w_lower = w.lower()
            # Numeric digits
            if re.match(r'^\d+(\.\d+)?$', w):
                qty = float(w)
                continue
            # Hindi/English number word
            if w_lower in NUMBER_WORDS:
                qty = float(NUMBER_WORDS[w_lower])
                continue
            # Skip noise words
            if w_lower in {"aaj", "today", "packet", "litre", "liter", "kg", "kilo", "gram", "gm", "box", "nag", "pe", "ka"}:
                continue
            if w_lower in SALE_KEYWORDS or w_lower in STOCK_IN_KEYWORDS:
                continue
            cleaned_words.append(w)

        if qty is None:
            qty = 1.0  # Default 1 unit if spoken without count

        candidate_name = " ".join(cleaned_words).strip()
        match_info = find_best_matching_product(db, candidate_name) if candidate_name else None

        if match_info:
            results.append({
                "raw_clause": clause_str,
                "action": action,
                "product_id": match_info["product_id"],
                "product_name": match_info["product_name"],
                "category": match_info["category"],
                "quantity": qty,
                "unit": match_info["unit"],
                "unit_price": match_info["selling_price"] if action == "SALE" else match_info["purchase_price"],
                "estimated_total": round(qty * (match_info["selling_price"] if action == "SALE" else match_info["purchase_price"]), 2),
                "confidence": match_info["match_confidence"],
                "needs_review": not match_info["is_confident"],
            })
        elif candidate_name:
            # Unmatched candidate
            results.append({
                "raw_clause": clause_str,
                "action": action,
                "product_id": None,
                "product_name": candidate_name.title(),
                "category": "Unassigned",
                "quantity": qty,
                "unit": "pack",
                "unit_price": 0.0,
                "estimated_total": 0.0,
                "confidence": 30.0,
                "needs_review": True,
            })

    return results


def parse_notebook_raw_text(db: Session, raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses handwritten register text or OCR lines.
    Format examples:
    '2026-09-30 | Milk 500ml | 5 pkts | 25'
    'Bread 4 112'
    'Cooking Oil - 2'
    """
    lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
    extracted = []

    for idx, line in enumerate(lines, start=1):
        # Ignore comments or headers
        if line.startswith("#") or "product" in line.lower() and "qty" in line.lower():
            continue

        # Split by pipe, comma, tab, or dash
        parts = re.split(r'[,|\t\-]+', line)
        parts = [p.strip() for p in parts if p.strip()]

        if not parts:
            continue

        date_val = None
        p_name = None
        qty = 1.0
        price = None
        notes = ""

        # Extract date if present
        date_match = re.search(r'\b\d{4}-\d{2}-\d{2}\b', line)
        if date_match:
            date_val = date_match.group(0)

        # Inspect parts
        for p in parts:
            if re.match(r'^\d{4}-\d{2}-\d{2}$', p):
                continue
            if re.match(r'^\d+(\.\d+)?$', p):
                num = float(p)
                if qty == 1.0:
                    qty = num
                elif price is None:
                    price = num
            elif not p_name:
                p_name = p
            else:
                notes = f"{notes} {p}".strip()

        if not p_name:
            continue

        match = find_best_matching_product(db, p_name)
        extracted.append({
            "line_number": idx,
            "raw_line": line,
            "date": date_val or "2026-09-30",
            "matched_product_id": match["product_id"] if match else None,
            "product_name": match["product_name"] if match else p_name.title(),
            "quantity": qty,
            "unit_price": price if price is not None else (match["selling_price"] if match else 0.0),
            "notes": notes or ("Verified" if match and match["is_confident"] else "Review product name"),
            "confidence": match["match_confidence"] if match else 40.0,
            "needs_review": match is None or not match["is_confident"] or price is None,
        })

    return extracted
