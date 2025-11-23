#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RV25J_Process OCR Pipeline and data processing
Author: Improved for modular maintainability

Pipeline:
   *_table.jpg  →  OCR (PP-Structure) or existing *_tblXX.md
                 →  parse HTML/MD table
                 →  clean numeric
                 →  detect closure
                 →  *_OCR.toml  <-- CORRECTED OUTPUT NAME
                 →  *_plot.png (REMOVED)

NOTE:
   - config.toml is MANDATORY in the root folder.
   - [Deed].EPSG and [Deed].Survey_Type are copied into the output TOML.
   - [META].DOL_Office is copied into the output TOML.
"""

import argparse
import re
from pathlib import Path
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup
from paddleocr import PPStructureV3 
import matplotlib.pyplot as plt
import numpy as np 
import pandas as pd

# ---- TOML reader (Python 3.11+ or older with tomli) -----------------
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # older Python
    import tomli as tomllib  # type: ignore


class RV25jProcessor:
    # REMOVED: COLUMN_SPEC = "MARKER,,NORTHING,EASTING".split(",") 

    def __init__(self, root_folder: str, skip_ocr: bool = False):
        self.root = Path(root_folder)
        self.skip_ocr = skip_ocr 
        self.pipeline = None
        self.config = {}
        # NEW: Initialize COLUMN_SPEC as None before loading config
        self.COLUMN_SPEC = None

        if not self.root.is_dir():
            raise ValueError(f"[ERROR] Folder not found: {self.root}")

        # -------------------------------
        # Load config.toml (MANDATORY)
        # -------------------------------
        cfg_path = self.root / "config.toml"
        if not cfg_path.is_file():
            raise SystemExit(f"[FATAL] config.toml not found in: {self.root}")

        try:
            with cfg_path.open("rb") as f:
                self.config = tomllib.load(f)
            print(f"[INFO] Loaded config.toml: {cfg_path}")
        except Exception as e:
            raise SystemExit(f"[FATAL] Failed to read/parse config.toml → {e}")

        # NEW: Load COLUMN_SPEC from config
        try:
            # We expect ["MRK_DOL", "NORTHING", "EASTING"] from the config
            self.COLUMN_SPEC = self.config["META"]["COLUMN_SPEC"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing key: [META].COLUMN_SPEC")

        # -------------------------------
        # Init OCR pipeline (if needed)
        # -------------------------------
        if not self.skip_ocr: 
            print("[INFO] Init PaddleOCR Thai PP-StructureV3...")
            self.pipeline = PPStructureV3(
                lang="th",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                use_table_recognition=True,
            )

    # -----------------------------------------------------------
    def get_prefix(self, image_path: Path) -> str:
        stem = image_path.stem
        return stem[:-len("_table")] if stem.endswith("_table") else stem

    # -----------------------------------------------------------
    def parse_markdown_table(self, md_path: Path) -> pd.DataFrame:
        html = md_path.read_text(encoding="utf-8", errors="ignore").strip()
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")

        if not table:
            print(f"[WARN] No <table> in {md_path}")
            return pd.DataFrame(columns=[c for c in self.COLUMN_SPEC if c])

        try:
            df_raw = pd.read_html(StringIO(str(table)))[0].reset_index(drop=True)
        except Exception as e:
            print(f"[WARN] pandas.read_html failed {md_path}: {e}")
            return pd.DataFrame(columns=[c for c in self.COLUMN_SPEC if c])

        df_raw = df_raw.map(
            lambda x: "" if pd.isna(x) else str(x).replace("\xa0", " ").strip()
        )

        out_cols = [c for c in self.COLUMN_SPEC if c]
        rows = []

        # Find the correct indices for the columns in the raw table (assuming a 1-to-1 mapping)
        # We need the indices of the input raw table columns that correspond to our desired columns.
        
        # Original logic assumed fixed indexing based on the split string "MARKER,,NORTHING,EASTING"
        # We need to adapt it to use the new list. 
        # Since we cannot inspect the raw HTML table structure here, we'll keep the loop structure 
        # but change the indices to refer to the raw dataframe columns (0, 1, 2, ...).
        # Assuming the data is in the order [MRK_DOL, NORTHING, EASTING] in the raw table columns 1, 2, 3...
        # Let's map raw column index to output name based on the old logic (where raw column 0 was MARKER, 2 was NORTHING, 3 was EASTING)
        
        # Map output column names to the index they should take from the raw DataFrame (adjusting for removal of blank columns)
        # If the input table only has 3 relevant columns, they are likely at indices 0, 1, 2. 
        
        # New mapping based on expected COLUMN_SPEC = [ "MRK_DOL" ,"NORTHING","EASTING" ]
        # Assumes raw table columns are [1, 2, 3] in order, which is the most common result for simple table OCR.
        
        # Since the original file used 'MARKER,,NORTHING,EASTING' which suggests ignoring raw index 1, 
        # let's assume raw column index 0 maps to 'MRK_DOL', 1 maps to 'NORTHING', and 2 maps to 'EASTING'
        # if the OCR output is clean. If the OCR table is a fixed width table, this mapping is key.
        
        # Original columns were: [0: MARKER, 1: (empty), 2: NORTHING, 3: EASTING]
        # New columns are: [0: MRK_DOL, 1: NORTHING, 2: EASTING]
        # This requires manually specifying the index mapping:

        COL_MAP = {
            self.COLUMN_SPEC[0]: 0, # MRK_DOL from raw column 0
            self.COLUMN_SPEC[1]: 1, # NORTHING from raw column 1
            self.COLUMN_SPEC[2]: 2  # EASTING from raw column 2
        }
        
        # We must use the indices of df_raw that correspond to the desired columns
        raw_col_indices = [idx for colname, idx in COL_MAP.items() if colname in self.COLUMN_SPEC]
        
        for _, row in df_raw.iterrows():
            rec = {}
            # Iterate through the desired column names in order
            for i, colname in enumerate(self.COLUMN_SPEC):
                if not colname:
                    continue

                raw_idx = raw_col_indices[i] if i < len(raw_col_indices) else -1
                
                raw = row.iloc[raw_idx].strip() if raw_idx != -1 and raw_idx < len(df_raw.columns) else ""
                val = (
                    raw.replace("O", "0")
                    .replace("o", "0")
                    .replace("I", "1")
                    .replace("i", "1")
                    .replace("l", "1")
                    .replace("L", "1")
                )

                if colname in ("NORTHING", "EASTING"):
                    cleaned = re.sub(r"[^0-9.]", "", val)
                    if cleaned.count(".") > 1:
                        first, *rest = cleaned.split(".")
                        cleaned = first + "." + "".join(rest)
                    try:
                        val = f"{float(cleaned):.3f}"
                    except Exception:
                        val = ""
                rec[colname] = val

            if any(rec.values()):
                rows.append(rec)

        return pd.DataFrame(rows, columns=out_cols)

    # -----------------------------------------------------------
    def run_ocr(self, image_path: Path) -> pd.DataFrame:
        prefix = self.get_prefix(image_path)
        out_img_dir = image_path.parent / "imgs"
        out_img_dir.mkdir(exist_ok=True)

        print(f"\n[INFO] OCR: {image_path}")
        outputs = self.pipeline.predict(str(image_path))

        dfs = []
        for i, res in enumerate(outputs):
            md_file = image_path.parent / f"{prefix}_tbl{i:02d}.md"
            res.save_to_markdown(save_path=str(md_file))
            res.save_to_img(save_path=str(out_img_dir))

            df = self.parse_markdown_table(md_file)
            if not df.empty:
                dfs.append(df)

        return (
            pd.concat(dfs, ignore_index=True)
            if dfs
            else pd.DataFrame(columns=self.COLUMN_SPEC)
        )

    # -----------------------------------------------------------
    def parse_existing_md(self, image_path: Path) -> pd.DataFrame:
        prefix = self.get_prefix(image_path)
        md_files = sorted(image_path.parent.glob(f"{prefix}_tbl*.md"))

        if not md_files:
            print(f"[WARN] No MD found: {image_path}")
            return pd.DataFrame(columns=[c for c in self.COLUMN_SPEC if c])

        dfs = [self.parse_markdown_table(md) for md in md_files]
        dfs = [df for df in dfs if not df.empty]
        return (
            pd.concat(dfs, ignore_index=True)
            if dfs
            else pd.DataFrame(columns=self.COLUMN_SPEC)
        )

    # -----------------------------------------------------------
    def _toml_escape(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # -----------------------------------------------------------
    def get_meta_and_deed_from_config(self):
        """
        Read DOL_Office from [META], Survey_Type and EPSG from [Deed].
        All are mandatory.
        """
        # META / DOL_Office
        try:
            meta = self.config["META"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing section: [META]")

        try:
            office = meta["DOL_Office"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing key: [META].DOL_Office")

        if not isinstance(office, str) or not office.strip():
            raise SystemExit(f"[FATAL] Invalid DOL_Office in config.toml: {office}")

        # Deed / Survey_Type + EPSG
        try:
            deed = self.config["Deed"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing section: [Deed]")

        try:
            survey_type = deed["Survey_Type"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing key: [Deed].Survey_Type")

        if not isinstance(survey_type, str) or not survey_type.strip():
            raise SystemExit(
                f"[FATAL] Invalid Survey_Type in config.toml: {survey_type}"
            )

        try:
            epsg = deed["EPSG"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing key: [Deed].EPSG")

        if isinstance(epsg, int):
            epsg_str = str(epsg)
        elif isinstance(epsg, str) and epsg.strip().isdigit():
            epsg_str = epsg.strip()
        else:
            raise SystemExit(f"[FATAL] Invalid EPSG value in config.toml: {epsg}")

        return office, survey_type, epsg_str

    # -----------------------------------------------------------
    def write_toml(self, image_path: Path, df: pd.DataFrame):
        """
        Build <prefix>_OCR.toml from OCR/MD DataFrame.
        Returns vertices list.
        """
        prefix = self.get_prefix(image_path)
        # CORRECTED OUTPUT NAME
        toml_path = image_path.with_name(f"{prefix}_OCR.toml") 

        vertices = []
        # Find the indices for NORTHING and EASTING in the DataFrame
        col_northing = self.COLUMN_SPEC[1] # Assuming NORTHING is always the second element
        col_easting = self.COLUMN_SPEC[2]  # Assuming EASTING is always the third element
        col_marker = self.COLUMN_SPEC[0] # Assuming MRK_DOL is the first element
        
        for _, r in df.iterrows():
            try:
                # Use the column names derived from config (MRK_DOL, NORTHING, EASTING)
                n = float(r[col_northing])
                e = float(r[col_easting])
                vertices.append({"marker": r[col_marker], "north": n, "east": e}) 
            except Exception:
                continue

        if not vertices:
            print(f"[WARN] No numeric rows: {image_path}")
            return [] 

        polygon_closed = False
        if len(vertices) >= 2:
            f, l = vertices[0], vertices[-1]
            # Simple closure check for TOML metadata
            if (
                abs(f["north"] - l["north"]) < 1e-3
                and abs(f["east"] - l["east"]) < 1e-3
                and f["marker"] == l["marker"]
            ):
                polygon_closed = True
                vertices = vertices[:-1]

        rows = []
        for idx, v in enumerate(vertices, start=1):
            label = chr(64 + idx) if idx <= 26 else f"P{idx}"
            rows.append([idx, label, v["marker"], v["north"], v["east"]])

        office, survey_type, epsg_str = self.get_meta_and_deed_from_config()

        lines = []

        # ---------------- [META] section ----------------
        lines.append("[META]")
        lines.append(f'DOL_Office = "{self._toml_escape(office)}"')
        lines.append("")  # blank line

        # ---------------- [Deed] section ----------------
        lines.append("[Deed]")
        lines.append(f'Survey_Type = "{self._toml_escape(survey_type)}"')
        lines.append(f"EPSG = {epsg_str}")
        lines.append('unit = "meter"')
        lines.append(
            f"polygon_closed = {'true' if polygon_closed else 'false'}"
        )
        lines.append("marker = [")

        for idx, label, name, n, e in rows:
            lines.append(
                f'  [{idx}, "{self._toml_escape(label)}", '
                f'"{self._toml_escape(name)}", {n:.3f}, {e:.3f}],'
            )
        lines.append("]")

        toml_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[OK] TOML → {toml_path}")
        return vertices 

    # -----------------------------------------------------------
    def process(self):
        images = sorted(self.root.rglob("*_table.jpg"))
        if not images:
            raise SystemExit("[ERROR] No *_table.jpg found")

        print(f"[INFO] Found {len(images)} files")

        for img in images:
            print("\n" + "=" * 70)
            print(f"[PROCESS] {img}")

            df = self.parse_existing_md(img) if self.skip_ocr else self.run_ocr(img) 

            if df.empty:
                print("[WARN] Empty DF from OCR/MD")
                continue
            
            self.write_toml(img, df) 

        print("\n[DONE] Processing complete.")


# ============================================================
# CLI Entry
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="RV25j OCR → TOML (Plotting Removed)")
    parser.add_argument("folder", help="Folder containing *_table.jpg")
    
    args = parser.parse_args()
    
    processor = RV25jProcessor(args.folder, skip_ocr=False) 
    processor.process()


if __name__ == "__main__":
    main()