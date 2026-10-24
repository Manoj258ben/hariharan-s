"""
StockSense Smart Data Import & Text-to-Structured Converter
Implements Section 3 of the master prompt with deterministic extraction heuristics.
"""
import os
import json
import re
import csv
import io
from typing import List, Dict, Any, Tuple, Optional
import httpx
from sqlalchemy.orm import Session
from ..models import Product

def try_gemini_extraction(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Attempts LLM structured extraction via Gemini API when GEMINI_API_KEY is configured.
    Converts unstructured bills, receipts, or notes into structured product rows.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    system_instruction = (
        "You are an expert retail data parser. Extract products, quantities, prices, barcodes, and expiry dates "
        "from the text into a JSON array of objects with keys: product_name, category, current_stock, purchase_price, "
        "selling_price, barcode, expiry_date. Return ONLY valid JSON."
    )
    payload = {
        "contents": [{
            "parts": [{"text": f"{system_instruction}\n\nRetail Text:\n{raw_text}"}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                items = json.loads(text_out)
                if isinstance(items, list):
                    for idx, it in enumerate(items, start=1):
                        it["product_id"] = f"P_AI_{idx:03d}"
                        it["warnings"] = []
                        it["extraction_method"] = "GEMINI_AI"
                        if "purchase_price" in it and "selling_price" not in it:
                            it["selling_price"] = round(float(it["purchase_price"]) * 1.25, 2)
                    return items
    except Exception as e:
        print(f"[Importer] Gemini extraction fallback triggered: {e}")
    return None

def extract_structured_from_unstructured_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses messy retail text, bills, WhatsApp supplier notes, or pasted tables.
    Extracts product name, barcode, quantities, prices, categories, and expiry dates.
    Uses Gemini AI if configured, otherwise uses deterministic heuristic patterns.
    """
    ai_result = try_gemini_extraction(raw_text)
    if ai_result:
        return ai_result

    lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
    parsed_items = []

    # Common kirana categories
    categories = ["Dairy", "Bakery", "Snacks", "Staples", "Beverages", "Household", "Produce", "Confectionery"]

    # Regex patterns
    barcode_pattern = re.compile(r"\b(\d{8,14})\b")
    date_pattern = re.compile(r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b")
    price_pattern = re.compile(r"(?:rs\.?|inr|₹|cost|price|sell)?\s*[:=]?\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE)

    for idx, line in enumerate(lines, start=1):
        if line.startswith("#") or line.startswith("//"):
            continue

        item = {
            "source_line": line,
            "product_id": f"P_IMP_{idx:03d}",
            "product_name": "",
            "category": "Staples",
            "current_stock": 0.0,
            "purchase_price": 0.0,
            "selling_price": 0.0,
            "barcode": None,
            "expiry_date": None,
            "warnings": []
        }

        # 1. Check for barcode
        b_match = barcode_pattern.search(line)
        if b_match:
            item["barcode"] = b_match.group(1)

        # 2. Check for date
        d_match = date_pattern.search(line)
        if d_match:
            item["expiry_date"] = d_match.group(1).replace("/", "-")

        # 3. Check for category keyword
        for cat in categories:
            if re.search(rf"\b{cat}\b", line, re.IGNORECASE):
                item["category"] = cat
                break

        # 4. Comma, pipe, tab, or semicolon separated
        tokens = [t.strip() for t in re.split(r"[,|\t;]+", line) if t.strip()]
        if len(tokens) >= 2:
            item["product_name"] = tokens[0]
            # Try to parse numeric fields
            nums = []
            for tok in tokens[1:]:
                tok_clean = re.sub(r"[^\d.]", "", tok)
                if tok_clean:
                    try:
                        nums.append(float(tok_clean))
                    except ValueError:
                        pass

            if len(nums) >= 3:
                item["current_stock"] = nums[0]
                item["purchase_price"] = nums[1]
                item["selling_price"] = nums[2]
            elif len(nums) == 2:
                item["current_stock"] = nums[0]
                item["selling_price"] = nums[1]
                item["purchase_price"] = round(nums[1] * 0.8, 2)
            elif len(nums) == 1:
                item["current_stock"] = nums[0]
        else:
            # Fallback regex word extraction
            words = line.split()
            item["product_name"] = " ".join(words[:min(3, len(words))])
            all_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", line)
            if all_numbers:
                item["current_stock"] = float(all_numbers[0])
                if len(all_numbers) > 1:
                    item["purchase_price"] = float(all_numbers[1])
                if len(all_numbers) > 2:
                    item["selling_price"] = float(all_numbers[2])

        # Default selling price if zero
        if item["selling_price"] == 0.0 and item["purchase_price"] > 0:
            item["selling_price"] = round(item["purchase_price"] * 1.25, 2)

        # Sanity validation warnings
        if not item["product_name"]:
            item["warnings"].append("Missing product name.")
        if item["purchase_price"] <= 0:
            item["warnings"].append("Zero purchase price.")
        if item["selling_price"] < item["purchase_price"]:
            item["warnings"].append("Selling price is lower than cost.")

        parsed_items.append(item)

    return parsed_items


def check_product_duplicates(db: Session, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Checks each incoming record against existing SQLite products by product_id, barcode, and name.
    """
    for r in records:
        r["is_duplicate"] = False
        r["duplicate_reason"] = None

        pid = r.get("product_id")
        barcode = r.get("barcode")
        name = r.get("product_name")

        if pid and db.query(Product).filter(Product.product_id == pid).first():
            r["is_duplicate"] = True
            r["duplicate_reason"] = f"Product ID '{pid}' already exists in SQLite."
        elif barcode and db.query(Product).filter(Product.barcode == barcode).first():
            r["is_duplicate"] = True
            r["duplicate_reason"] = f"Barcode '{barcode}' already assigned to another product."
        elif name and db.query(Product).filter(Product.product_name.ilike(name)).first():
            r["is_duplicate"] = True
            r["duplicate_reason"] = f"Product with name '{name}' already exists in database."

    return records
