#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RV25J_Process OCR Pipeline and data processing
Author: Improved for modular maintainability

Pipeline:
    *_table.jpg  →  OCR (PP-Structure) or existing *_tblXX.md
                  →  parse HTML/MD table
                  →  CLEAN BLANK COLUMNS (NEW)
                  →  CALCULATE COORDINATES: Meter + Fraction/1000 (NEW)
                  →  clean numeric
                  →  detect closure
                  →  *_OCR.toml  <-- CORRECTED OUTPUT NAME
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

# ---- TOML reader (Python 3.11+ or older with tomli) -----------------
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # older Python
    import tomli as tomllib  # type: ignore


# ---- Helper Function for robust float conversion ----
def safe_float(s):
    """Converts string to float, handles empty string, and cleans non-digit/dot chars."""
    if not isinstance(s, str) or not s.strip():
        return np.nan
    try:
        # Clean non-numeric characters first (except for '.')
        cleaned = re.sub(r"[^0-9.]", "", s)
        
        # Handle multiple dots (keeping the first one)
        if cleaned.count(".") > 1:
            first, *rest = cleaned.split(".")
            cleaned = first + "." + "".join(rest)
            
        return float(cleaned)
    except Exception:
        return np.nan
# -----------------------------------------------------


class RV25jProcessor:
    def __init__(self, root_folder: str, skip_ocr: bool = False):
        self.root = Path(root_folder)
        self.skip_ocr = skip_ocr
        self.pipeline = None
        self.config = {}
        self.COLUMN_SPEC = None

        if not self.root.is_dir():
            raise ValueError(f"[ERROR] Folder not found: {self.root}")

        # Load config.toml (MANDATORY)
        cfg_path = self.root / "config.toml"
        if not cfg_path.is_file():
            raise SystemExit(f"[FATAL] config.toml not found in: {self.root}")

        try:
            with cfg_path.open("rb") as f:
                self.config = tomllib.load(f)
        except Exception as e:
            raise SystemExit(f"[FATAL] Failed to read/parse config.toml → {e}")

        # NEW: Load COLUMN_SPEC from config
        try:
            # Assuming COLUMN_SPEC is something like ['MARKER', 'NORTHING', 'EASTING']
            self.COLUMN_SPEC = self.config["META"]["COLUMN_SPEC"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing key: [META].COLUMN_SPEC")

        # Init OCR pipeline (if needed)
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

    def _ColumnMeterFraction(self, df_raw) -> pd.DataFrame:
        # --- Step 3: Calculation of NORTHING/EASTING (Meters + Fraction/1000) ---
        
        # 3a. Rename columns for explicit calculation
        coord_map = {
            df_raw.columns[0]: self.COLUMN_SPEC[0], # Marker Name (e.g., 'MRK_DOL')
            df_raw.columns[5]: 'N_M',    # Column 6: Northing Meters
            df_raw.columns[6]: 'N_F',    # Column 7: Northing Fraction
            df_raw.columns[7]: 'E_M',    # Column 8: Easting Meters
            df_raw.columns[8]: 'E_F',    # Column 9: Easting Fraction
        }
        # Note: If blank columns were dropped, these indices (6, 7, 8, 9) might be incorrect.
        # This implementation assumes the critical columns remain at these fixed indices 
        # relative to the original raw table structure.
        df_raw.rename(columns=coord_map, inplace=True)
        
        # 3b. Apply OCR correction (O->0, I->1, etc.) and safe float conversion
        coord_cols = ['N_M', 'N_F', 'E_M', 'E_F']
        for col in coord_cols:
            if col in ['N_M', 'N_F', 'E_M', 'E_F']:
                # Apply safe_float (includes internal cleaning) for numeric data
                df_raw[col] = df_raw[col].apply(safe_float)
            else:
                # Apply OCR correction for marker name column
                df_raw[col] = df_raw[col].astype(str).str.replace('O', '0').str.replace('o', '0').str.replace('I', '1').str.replace('i', '1').str.replace('l', '1').str.replace('L', '1').str.strip()
        # 3c. Calculate final coordinates
        df_raw[self.COLUMN_SPEC[1]] = df_raw['N_M'] + (df_raw['N_F'] / 1000.0)
        df_raw[self.COLUMN_SPEC[2]] = df_raw['E_M'] + (df_raw['E_F'] / 1000.0)
        return df_raw

    # -----------------------------------------------------------
    def parse_markdown_table(self, md_path: Path) -> pd.DataFrame:
        MRK_COL,N_COL,E_COL = self.COLUMN_SPEC 
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

        # Step 1: Clean up strings (strip whitespace, replace non-breaking space)
        df_raw = df_raw.map(
            lambda x: "" if pd.isna(x) else str(x).replace("\xa0", " ").strip()
        )

        # Step 2: Identify and drop columns that are entirely blank
        cols_to_drop = [
            col for col in df_raw.columns
            if all(val == "" for val in df_raw[col])
        ]

        if cols_to_drop:
            print(f"[INFO] Dropping blank columns: {cols_to_drop}")
            df_raw = df_raw.drop(columns=cols_to_drop)

        # Ensure we have at least 10 columns (Marker + 4 coordinate pairs * 2 = 9 columns minimum)
        if len(df_raw.columns) == 9:
            df_raw = self._ColumnMeterFraction(df_raw)
        else:
            COL_N = len(df_raw)
            coord_map = {
                df_raw.columns[ 0]: MRK_COL, # Marker Name (e.g., 'MRK_DOL')
                df_raw.columns[-2]: N_COL, #  Northing Meters
                df_raw.columns[-1]: E_COL, #  Easting Meters
                }
            df_raw.rename(columns=coord_map, inplace=True)

        #import pdb ;pdb.set_trace()
        # --- Step 4: Final Cleaning and Filtering ---

        # 4a. Explicitly ensure calculated coordinates are clean floats 
        # (This is a safeguard, though calculation result is float)
        for col in [N_COL, E_COL]:
            # Strip all spaces from string representation (for robustness against strange formatting)
            df_raw[col] = df_raw[col].astype(str).str.replace(' ', '', regex=False).str.strip()
            # Convert the result to float, coercing errors to NaN
            df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')
        
        # 4b. Filter out rows where both calculated coordinates are NaN
        df_raw.dropna(subset=[N_COL, E_COL], how='all', inplace=True)

        # 4c. Remove all extra columns, keeping only the final required columns
        out_cols = [c for c in self.COLUMN_SPEC if c] 
        # Select ONLY the final required columns
        df_final = df_raw[out_cols].copy() 

        # --- Step 5: Final Formatting for TOML output ---
        rows = []
        marker_col = self.COLUMN_SPEC[0]
        
        for _, rec in df_final.iterrows():
            rec_dict = rec.to_dict() 
            
            # Format coordinates to 3 decimal places
            try:
                rec_dict[N_COL] = f"{rec_dict[N_COL]:.3f}"
            except Exception:
                rec_dict[N_COL] = ""
            
            try:
                rec_dict[E_COL] = f"{rec_dict[E_COL]:.3f}"
            except Exception:
                rec_dict[E_COL] = ""
            
            # Final check and stripping for marker
            rec_dict[MRK_COL] = str(rec_dict[MRK_COL]).strip()

            # Filter: Only append rows that have at least one valid coordinate value
            if rec_dict[N_COL] or rec_dict[E_COL]:
                rows.append(rec_dict)

        return pd.DataFrame(rows, columns=out_cols)

    # -----------------------------------------------------------
    # The rest of the class methods (run_ocr, parse_existing_md, 
    # _toml_escape, get_meta_and_deed_from_config, write_toml, process)
    # remain unchanged from the original script, except they now use the 
    # corrected output from parse_markdown_table.
    # -----------------------------------------------------------

    # ... (find_images, filter_images, list_files methods unchanged) ...
    def find_images(self) -> list[Path]:
        """Helper to return sorted list of matching images."""
        return sorted(self.root.rglob("*_table.jpg"))

    def filter_images(self, images: list[Path], range_str: str) -> list[Path]:
        """
        Filters the list of images based on a 1-based range string 'start,end'.
        Example: "4,6" -> returns images at index 3, 4, 5 (User's 4, 5, 6)
        """
        if not range_str:
            return images

        total = len(images)
        try:
            if "," in range_str:
                parts = range_str.split(",")
                if len(parts) != 2:
                    raise ValueError
                start_idx = int(parts[0].strip())
                end_idx = int(parts[1].strip())
            else:
                # Single number case
                start_idx = int(range_str.strip())
                end_idx = start_idx

            # Bounds checking (Clamp values)
            if start_idx < 1: start_idx = 1
            if end_idx > total: end_idx = total
            
            if start_idx > end_idx:
                print(f"[WARN] Invalid range {start_idx}-{end_idx}. Processing nothing.")
                return []

            # Convert 1-based user input to 0-based Python slice
            # Slice is [start-1 : end]
            subset = images[start_idx-1 : end_idx]
            
            print(f"[INFO] Image Range: {start_idx} to {end_idx} (Selected {len(subset)} files)")
            return subset

        except ValueError:
            print(f"[ERROR] Invalid format for -i/--images: '{range_str}'. Expected 'start,end' (e.g. '4,6')")
            raise SystemExit(1)

    def list_files(self):
        """Lists all matching files with Index IDs and exits."""
        images = self.find_images()
        if not images:
            print(f"[INFO] No *_table.jpg found in: {self.root}")
            return

        print(f"[INFO] Found {len(images)} files in: {self.root}")
        print("-" * 60)
        for idx, img in enumerate(images, start=1):
            try:
                display_path = img.relative_to(self.root)
            except ValueError:
                display_path = img
            # Display index number [N] to help user select range
            print(f"[{idx}] {display_path}")
        print("-" * 60)

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
        try:
            meta = self.config["META"]
            office = meta["DOL_Office"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing [META] or DOL_Office")

        if not isinstance(office, str) or not office.strip():
            raise SystemExit(f"[FATAL] Invalid DOL_Office: {office}")

        try:
            deed = self.config["Deed"]
            survey_type = deed["Survey_Type"]
            epsg = deed["EPSG"]
        except KeyError:
            raise SystemExit("[FATAL] config.toml missing [Deed], Survey_Type or EPSG")

        if not isinstance(survey_type, str) or not survey_type.strip():
            raise SystemExit(f"[FATAL] Invalid Survey_Type: {survey_type}")

        if isinstance(epsg, int):
            epsg_str = str(epsg)
        elif isinstance(epsg, str) and epsg.strip().isdigit():
            epsg_str = epsg.strip()
        else:
            raise SystemExit(f"[FATAL] Invalid EPSG: {epsg}")

        return office, survey_type, epsg_str

    # -----------------------------------------------------------
    def write_toml(self, image_path: Path, df: pd.DataFrame):
        prefix = self.get_prefix(image_path)
        toml_path = image_path.with_name(f"{prefix}_OCR.toml")

        vertices = []
        MRK_COL,N_COL,E_COL = self.COLUMN_SPEC

        # Note: df now only contains the three required columns (e.g., Marker, Northing, Easting)
        for _, r in df.iterrows():
            try:
                # The values are strings in '0.000' format
                n = float(r[N_COL])
                e = float(r[E_COL])
                vertices.append({"marker": r[MRK_COL], "north": n, "east": e})
            except Exception:
                continue

        if not vertices:
            print(f"[WARN] No numeric rows: {image_path}")
            return []
       
        rows = []
        for idx, v in enumerate(vertices, start=1):
            label = chr(64 + idx) if idx <= 26 else f"P{idx}"
            rows.append([idx, label, v["marker"], v["north"], v["east"]])

        office, survey_type, epsg_str = self.get_meta_and_deed_from_config()

        lines = []
        lines.append("[META]")
        lines.append(f'DOL_Office = "{self._toml_escape(office)}"')
        lines.append("")
        lines.append("[Deed]")
        lines.append('ParcelNumber = "000"')
        lines.append('MapSheet = "DDDD-II-DDDD"')
        lines.append(f'Survey_Type = "{self._toml_escape(survey_type)}"')
        lines.append(f"EPSG = {epsg_str}")
        lines.append('unit = "meter"')
        lines.append(f'area_grid = "rai-ngan-wa"')
        lines.append(f'area_topo = "rai-ngan-wa"')
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
    def process(self, image_range: str = None):
        all_images = self.find_images()
        if not all_images:
            raise SystemExit("[ERROR] No *_table.jpg found")

        # FILTER IMAGES IF RANGE IS PROVIDED
        images_to_process = self.filter_images(all_images, image_range)

        if not images_to_process:
            print("[INFO] No images to process based on filter.")
            return

        print(f"[INFO] Processing {len(images_to_process)} / {len(all_images)} detected files.")

        for img in images_to_process:
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
    parser = argparse.ArgumentParser(description="RV25j OCR → TOML")
    parser.add_argument("folder", help="Folder containing *_table.jpg")
    parser.add_argument(
        "-s", "--skip-ocr",
        action="store_true",
        help="Skip the OCR process and use existing *_tbl*.md files for parsing."
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all matching files with ID numbers and exit."
    )
    # ADDED: Images range argument
    parser.add_argument(
        "-i", "--images",
        type=str,
        help="Range of image numbers to process (e.g., '4,6' for 4, 5, 6). Use -l to see numbers."
    )
    
    args = parser.parse_args()
    
    # Force skip_ocr if we are only listing files
    processor = RV25jProcessor(args.folder, skip_ocr=(args.skip_ocr or args.list))
    
    if args.list:
        processor.list_files()
    else:
        processor.process(image_range=args.images)


if __name__ == "__main__":
    main()