import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import os
import shutil
import json
from PIL import Image, ImageTk
# For local plotting functionality (re-included from previous steps)
try:
    import matplotlib.pyplot as plt 
    import numpy as np             
    import pandas as pd 
except ImportError:
    plt = np = pd = None 
    
try:
    import tomllib 
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from toml_editor import TOMLTextEditor 

# --- Configuration Constants ---
DEFAULT_FONT = ('Tahoma', 10)
TEXT_WIDTH = 35  
TEXT_HEIGHT = 10 
# --- Global Configuration Option ---
USE_SIMULATED_TOML = False 

# --- SIMULATED OCR DATA (Remains for button logic fallback) ---
SIMULATED_OCR_TOML_CONTENT = """[META]
DOL_Office = "Narathivas"

[Deed]
Survey_Type = "MAP-L1"
EPSG = 24047
unit = "meter"
polygon_closed = false
marker = [
  [1, "A", "s41", 711042.723, 810293.807],
  [2, "B", "520", 711275.096, 810520.089],
  [3, "C", "s21", 711325.209, 810466.417],
  [4, "D", "19", 711354.507, 810440.839],
  [5, "E", "s24", 711494.218, 810313.001],
  [6, "F", "$23", 711488.109, 810300.804],
  [7, "G", "s22", 711328.714, 810147.726],
  [8, "H", "s42", 711420.856, 810053.505],
  [9, "I", "S43", 711349.998, 809983.554],
  [10, "J", "541", 711042.723, 810293.807],
]
"""

class OCRTomlEditor(ttk.Frame):
    """
    Component for the right-hand sub-frame managing the OCR process:
    1. Displaying raw OCR output (read-only)
    2. Displaying editable verification output (R/W)
    3. Displaying a plot image (*_plot.png)
    """
    def __init__(self, master=None, log_callback=None, column_spec=None, **kwargs):
        super().__init__(master, **kwargs)
        self.log_callback = log_callback if log_callback else print
        
        # FIX: Store the passed-in column specification from config.toml
        # Expected structure: ["MRK_DOL", "NORTHING", "EASTING"]
        self.COLUMN_SPEC = column_spec if column_spec is not None else []
        #import pdb; pdb.set_trace()
        # Expects *_RV25J.jpg
        self.current_image_path: Path = None  
        self.plot_tk_image = None 
        self.current_plot_path: Path = None 

        self.columnconfigure(0, weight=1)
        

        self._create_widgets()
        self.reset_editors()
        # Bind resize event which is needed for plotting functionality
        self.plot_canvas.bind('<Configure>', self.on_plot_canvas_resize)


    def log(self, message):
        """Wrapper for the log callback."""
        self.log_callback(message)

    def _create_widgets(self):
        """Creates the two TOML editors and the plot image placeholder."""

        # --- 1. Raw OCR Output Editor (Top) ---
        ttk.Label(self, text="1. Raw OCR Output (*_OCR.toml)", font=DEFAULT_FONT).grid(row=0, column=0, sticky='w', padx=5, pady=(5, 0))
        
        self.raw_ocr_editor = TOMLTextEditor(
            self,
            width=TEXT_WIDTH,
            height=TEXT_HEIGHT,
            font_family=DEFAULT_FONT[0],
            font_size=DEFAULT_FONT[1],
            background='#f0f0f0'
        )
        self.raw_ocr_editor.grid(row=1, column=0, sticky='nsew', padx=5, pady=(0, 5))
        self.raw_ocr_editor.config(state=tk.DISABLED) # Always read-only
        # NEW: Ensure Raw OCR Editor Row expands
        self.grid_rowconfigure(1, weight=1)

        # --- 2. Verification Editor (Middle) ---
        ttk.Label(self, text="2. Verification/Edit (*_OCRedit.toml)", font=DEFAULT_FONT).grid(row=2, column=0, sticky='w', padx=5, pady=(5, 0))
        
        self.edit_ocr_editor = TOMLTextEditor(
            self,
            width=TEXT_WIDTH,
            height=TEXT_HEIGHT,
            font_family=DEFAULT_FONT[0],
            font_size=DEFAULT_FONT[1],
            background='yellow' 
        )
        self.edit_ocr_editor.grid(row=3, column=0, sticky='nsew', padx=5, pady=(0, 5))
        self.edit_ocr_editor.config(state=tk.DISABLED, background='#f0f0f0') 
        # NEW: Ensure Verification Editor Row expands equally
        self.grid_rowconfigure(3, weight=1)
        
        # --- 3. Plot Image Viewer (Bottom) ---
        ttk.Label(self, text="3. Plot Visualization (*_plot.png) & Markers", font=DEFAULT_FONT).grid(row=4, column=0, sticky='w', padx=5, pady=(5, 0))

        self.plot_canvas = tk.Canvas(
            self, 
            bg='white', 
            relief=tk.SUNKEN, 
            height=200 
        )
        self.plot_canvas.grid(row=5, column=0, sticky='nsew', padx=5, pady=(0, 5))
        # Keep plot area expansion
        self.grid_rowconfigure(5, weight=1) 
        
    def on_plot_canvas_resize(self, event):
        """
        Handles canvas resize event by reloading and scaling the current plot image.
        """
        if self.current_plot_path and event.width > 1 and event.height > 1:
            self.log(f"Action: Rescaling plot image due to resize to {event.width}x{event.height}")
            if self.current_plot_path.exists():
                self.load_plot_image(self.current_plot_path)

    def reset_editors(self):
        """Clears content and disables the editors."""
        self.raw_ocr_editor.config(state=tk.NORMAL)
        self.edit_ocr_editor.config(state=tk.NORMAL, background='yellow')
        
        self.raw_ocr_editor.set_content("# No OCR data loaded.")
        self.edit_ocr_editor.set_content("# Press 'OCR' to generate data.")
        
        self.raw_ocr_editor.config(state=tk.DISABLED)
        self.edit_ocr_editor.config(state=tk.DISABLED, background='#f0f0f0')
        
        self.plot_canvas.delete(tk.ALL)
        self.plot_tk_image = None
        self.current_plot_path = None 
        self.plot_canvas.create_text(
            self.plot_canvas.winfo_width() / 2, self.plot_canvas.winfo_height() / 2, 
            text="Plot Image Area", fill="#666", anchor=tk.CENTER
        )

    def load_files(self, parent_dir: Path, base_name_str: str):
        """
        Loads the corresponding *_OCR.toml, *_OCRedit.toml, and *_plot.png 
        for the given directory and base file name.
        """
        # Expects *.jpg source image
        self.current_image_path = parent_dir / f"{base_name_str}_RV25J.jpg"
        
        ocr_toml_path = parent_dir / f"{base_name_str}_OCR.toml"
        edit_toml_path = parent_dir / f"{base_name_str}_OCRedit.toml"
        
        # FIX 1: The plot file name is now derived from the parent directory name for robustness.
        plot_png_path = parent_dir / f"{parent_dir.name}_plot.png" 
        
        self.reset_editors()
        
        # --- Load Raw OCR TOML (with logging) ---
        self.log(f"I/O READ: Checking for Raw OCR TOML: {ocr_toml_path.name}")
        if ocr_toml_path.exists():
            try:
                raw_content = ocr_toml_path.read_text(encoding='utf-8')
                self.raw_ocr_editor.config(state=tk.NORMAL)
                self.raw_ocr_editor.set_content(raw_content)
                self.raw_ocr_editor.config(state=tk.DISABLED)
                self.log(f"SUCCESS: Loaded raw OCR TOML from {ocr_toml_path.name}.")
            except Exception as e:
                self.log(f"ERROR: Failed to read raw OCR TOML {ocr_toml_path.name}: {e}")
        else:
            self.log(f"WARNING: Raw OCR TOML not found: {ocr_toml_path.name}.")

        # --- Load Editable TOML (with logging and file copy logic) ---
        self.log(f"I/O READ: Checking for Editable TOML: {edit_toml_path.name}")
        if edit_toml_path.exists():
            try:
                edit_content = edit_toml_path.read_text(encoding='utf-8')
                self.edit_ocr_editor.config(state=tk.NORMAL)
                self.edit_ocr_editor.set_content(edit_content)
                self.edit_ocr_editor.config(state=tk.DISABLED, background='#f0f0f0') 
                self.log(f"SUCCESS: Loaded editable TOML from {edit_toml_path.name}.")
            except Exception as e:
                self.log(f"ERROR: Failed to read editable TOML {edit_toml_path.name}: {e}")
        elif ocr_toml_path.exists():
            try:
                self.log(f"I/O WRITE: Copying {ocr_toml_path.name} to {edit_toml_path.name}")
                shutil.copy(ocr_toml_path, edit_toml_path)
                edit_content = ocr_toml_path.read_text(encoding='utf-8')
                self.edit_ocr_editor.config(state=tk.NORMAL)
                self.edit_ocr_editor.set_content(edit_content)
                self.edit_ocr_editor.config(state=tk.DISABLED, background='#f0f0f0')
                self.log(f"SUCCESS: Copied {ocr_toml_path.name} to {edit_toml_path.name} for editing.")
            except Exception as e:
                self.log(f"ERROR: Failed to copy OCR TOML for editing: {e}")
        
        # --- Plotting ---
        self.current_plot_path = plot_png_path 

        # 1. Load existing plot image immediately if it exists (for redraw)
        self.log(f"I/O READ: Checking for Plot Image: {plot_png_path.name}")
        self.load_plot_image(plot_png_path) 
        
        # 2. Re-create the plot based on the TOML data (this overwrites the file 
        #    and calls load_plot_image again if successful).
        if edit_toml_path.exists() and plt is not None:
             self.create_parcel_plot(edit_toml_path)
        

    def load_plot_image(self, plot_path: Path):
        """Loads and scales the plot image to fit the canvas."""
        
        if plot_path == self.current_plot_path:
             self.plot_canvas.delete(tk.ALL)
             self.plot_tk_image = None
        
        if plot_path.exists():
            try:
                self.log(f"I/O READ: Reading plot image {plot_path.name}.")
                
                pil_image = Image.open(plot_path)
                
                self.update_idletasks()
                canvas_w = self.plot_canvas.winfo_width()
                canvas_h = self.plot_canvas.winfo_height()
                
                img_w, img_h = pil_image.size
                
                scale = min(canvas_w / img_w, canvas_h / img_h)
                
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                
                if scale < 1.0:
                    resized_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                else:
                    resized_image = pil_image
                
                self.plot_tk_image = ImageTk.PhotoImage(resized_image)
                
                x_center = (canvas_w - new_w) // 2
                y_center = (canvas_h - new_h) // 2
                
                self.plot_canvas.create_image(x_center, y_center, image=self.plot_tk_image, anchor=tk.NW)
                self.log(f"SUCCESS: Loaded plot image {plot_path.name} at {new_w}x{new_h}.")

            except Exception as e:
                self.log(f"ERROR: Failed to load plot image {plot_path.name}: {e}")
        else:
            self.plot_canvas.create_text(
                self.plot_canvas.winfo_width() / 2, self.plot_canvas.winfo_height() / 2, 
                text=f"Plot Image Not Found: {plot_path.name}", fill="#888", anchor=tk.CENTER
            )
            self.log(f"INFO: Plot image not found: {plot_path.name}. (Expected during initial load or before plotting)")
    
    def _extract_and_parse_markers(self, toml_path: Path) -> list[list]:
        """
        Reads the TOML file and extracts the marker array using the tomllib library.
        """
        if tomllib is None:
            self.log("ERROR: 'tomllib' is required. Cannot parse TOML.")
            return []

        if not toml_path.exists():
            self.log(f"WARNING: TOML file not found: {toml_path.name}.")
            return []

        try:
            self.log(f"INFO: Using tomllib to parse {toml_path.name}.")
            
            with open(toml_path, 'rb') as f:
                toml_data = tomllib.load(f)

            marker_data = toml_data.get('Deed', {}).get('marker')
            
            if marker_data is None:
                self.log(f"WARNING: 'Deed.marker' array not found in {toml_path.name}.")
                return []
                
            return marker_data
            
        except Exception as e:
            self.log(f"ERROR: Failed to parse markers from {toml_path.name}: {e}")
            return []

    def create_parcel_plot(self, toml_path: Path):
        """
        Creates a Matplotlib plot of the UTM markers by reading data into a Pandas DataFrame,
        draws a red polygon, adds axis labels, and saves the result to *_plot.png.
        """
        if plt is None or pd is None or np is None:
            self.log("ERROR: Matplotlib, NumPy, or Pandas library not imported/installed. Cannot generate plot.")
            return

        marker_data = self._extract_and_parse_markers(toml_path)
        
        if not marker_data:
            self.log("WARNING: Cannot create plot. No marker data available.")
            return

        df = pd.DataFrame(marker_data)
        
        # FIX 2: Dynamically set columns using ['NUM_SEQ', 'MRK_SEQ'] + self.COLUMN_SPEC
        # This structure must match the 5 items in marker_data: [ID, Label, MRK_DOL, Northing, Easting]
        expected_columns = ['NUM_SEQ', 'MRK_SEQ'] + [ "MRK_DOL" ,"NORTHING","EASTING" ]
        self.log( f"create_parcel_plot(): {expected_columns}" )
        expected_count = len(expected_columns)
        actual_count = len(df.columns)
        
        if actual_count == expected_count:
            df.columns = expected_columns
        else:
            self.log(f"WARNING: Plotting skipped. Mismatched column count in TOML data.")
            self.log(f"Expected {expected_count} columns but found {actual_count} in marker data. Check TOML structure.")
            return # Exit the function if column count is wrong.

        self.log(f"INFO: Markers loaded into Pandas DataFrame ({len(df)} rows).")
        
        # Define column names based on the configured specification for plot access
        col_easting = "EASTING"
        col_northing = "NORTHING"
        col_marker = "MRK_DOL"

        easting = df[col_easting].tolist()
        northing = df[col_northing].tolist()

        if easting[0] != easting[-1] or northing[0] != northing[-1]:
             easting.append(easting[0])
             northing.append(northing[0])
        
        parent_dir = toml_path.parent
        base_name_str = parent_dir.name 
        plot_png_path = parent_dir / f"{base_name_str}_plot.png" 
        
        try:
            plt.figure(figsize=(6, 5), facecolor='white')
            ax = plt.gca()
            ax.set_facecolor('white')
            
            ax.plot(easting, northing, color='red', linewidth=2, marker='o', markersize=4)
            
            x_arr = np.array(easting)
            y_arr = np.array(northing)
            ax.fill(x_arr, y_arr, color='red', alpha=0.1)

            for _, row in df.iterrows():
                # Label format: (MRK_SEQ)MRK_DOL
                # Accessing 'MRK_SEQ' directly as it's the second fixed column name
                label = f"{row['MRK_SEQ']}: {row[col_marker]}"
                
                ax.text(
                    row[col_easting], 
                    row[col_northing] + (northing[-1] - northing[0]) * 0.005, 
                    label, 
                    color='blue', 
                    fontsize=16, 
                    ha='center', 
                    va='bottom'
                )

            ax.set_xlabel(f'{col_easting} (m)')
            ax.set_ylabel(f'{col_northing} (m)')
            ax.set_title(f"Parcel Plot: {toml_path.name}")
            ax.grid(True, linestyle='--', alpha=0.6) 
            ax.set_aspect('equal', adjustable='box') 
            
            self.log(f"I/O WRITE: Creating Matplotlib plot and saving to {plot_png_path.name}")
            plt.savefig(plot_png_path, bbox_inches='tight', facecolor='white')
            plt.close()

            self.log(f"SUCCESS: Created Matplotlib plot and saved to {plot_png_path.name}")
            
            self.current_plot_path = plot_png_path 
            self.load_plot_image(plot_png_path)

        except Exception as e:
            self.log(f"ERROR creating Matplotlib plot: {e}")

    def on_save_or_edit_click(self):
        """
        Toggles the editor state: saves when switching from editable to read-only, 
        or enables editing when switching from read-only.
        """
        if self.edit_ocr_editor.cget('state') == tk.NORMAL:
            # Currently editing -> Perform Save and Disable
            save_successful = self.save_edited_toml()
            if save_successful:
                # Reload/Regenerate plot after successful save
                parent_dir = self.current_image_path.parent
                
                # Use the directory name to find the correct TOML file name
                base_name_for_toml = self.current_image_path.stem
                if base_name_for_toml.lower().endswith('_rv25j'):
                    base_name_for_toml = base_name_for_toml[:-6]
                
                edit_toml_path = parent_dir / f"{base_name_for_toml}_OCRedit.toml"
                #import pdb ;pdb.set_trace()
                if plt is not None:
                     self.create_parcel_plot(edit_toml_path)
                
                self.edit_ocr_editor.config(background='#f0f0f0') 
                self.log("Action: Verification TOML editor disabled (Saved).")
        else:
            # Currently disabled -> Enable Editing
            self.edit_ocr_editor.config(state=tk.NORMAL, background='yellow')
            self.log("Action: Verification TOML editor enabled.")

    def OCR_Process(self, is_all: bool):
        """
        Simulates the backend OCR process and writes results to *_OCR.toml, 
        or skips if USE_SIMULATED_TOML is False.
        """
        if not self.current_image_path:
            self.log("ERROR: No image selected to run OCR.")
            return False

        # Check the global flag
        if not USE_SIMULATED_TOML:
            self.log("INFO: Skipping simulated OCR process. Relying on external *_OCR.toml.")
            return True

        parent_dir = self.current_image_path.parent
        base_name_str = self.current_image_path.stem
        if base_name_str.lower().endswith('_rv25j'):
            base_name_str = base_name_str[:-6] 

        ocr_toml_path = parent_dir / f"{base_name_str}_OCR.toml"
        
        try:
            self.log(f"I/O WRITE: Writing simulated OCR data to {ocr_toml_path.name}")
            with open(ocr_toml_path, 'w', encoding='utf-8') as f:
                f.write(SIMULATED_OCR_TOML_CONTENT)
            
            self.log(f"SUCCESS: Simulated OCR result saved to {ocr_toml_path.name}.")
            return True
        except Exception as e:
            self.log(f"ERROR saving simulated OCR TOML: {e}")
            return False


    def on_ocr_click(self, is_all=False):
        """
        Handles the event when OCR buttons are clicked.
        """
        if not self.current_image_path:
            self.log("ERROR: No image selected to run OCR.")
            return

        if is_all:
            self.log("Action: Running OCR on ALL files (SIMULATED/EXTERNAL).")
            process_success = self.OCR_Process(is_all=True)
        else:
            self.log(f"Action: Running OCR on current image (SIMULATED/EXTERNAL): {self.current_image_path.name}")
            process_success = self.OCR_Process(is_all=False)
            
        if process_success:
            parent_dir = self.current_image_path.parent
            base_name_str = self.current_image_path.stem
            if base_name_str.lower().endswith('_rv25j'):
                base_name_str = base_name_str[:-6] 
                
            # Reload files to display the newly created/expected *_OCR.toml
            self.load_files(parent_dir, base_name_str)
        
    def save_edited_toml(self):
        """
        Saves the content of the editable TOML back to *_OCRedit.toml 
        and disables the editor.
        """
        if self.edit_ocr_editor.cget('state') == tk.DISABLED:
            self.log("ERROR: Cannot save. Editor is disabled. Click 'Edit/Save TOML' first.")
            return False
        
        if not self.current_image_path:
            self.log("ERROR: No current image path available for saving.")
            return False

        # 1. Derive file path 
        parent_dir = self.current_image_path.parent
        base_name_str = self.current_image_path.stem
        if base_name_str.lower().endswith('_rv25j'):
            base_name_str = base_name_str[:-6]
            
        edit_toml_path = parent_dir / f"{base_name_str}_OCRedit.toml"
        
        # 2. Get content
        content = self.edit_ocr_editor.get_content()

        # 3. Save
        try:
            edit_toml_path.write_text(content, encoding='utf-8')
            self.log(f"SUCCESS: Verification TOML saved to {edit_toml_path.name}.")
            self.edit_ocr_editor.config(state=tk.DISABLED)
            return True
        except Exception as e:
            self.log(f"ERROR saving editable TOML: {e}")
            return False

# Simple utility to ensure TOMLTextEditor is available if needed for local testing
try:
    from toml_editor import TOMLTextEditor
except ImportError:
    # Minimal dummy class for local testing if toml_editor.py isn't present
    class TOMLTextEditor(tk.Text):
        def __init__(self, master=None, *args, **kwargs):
            tk.Text.__init__(self, master, *args, **kwargs)
            self.insert(tk.END, "TOML Editor Dummy")
        def set_content(self, text):
            self.config(state=tk.NORMAL)
            self.delete('1.0', tk.END)
            self.insert('1.0', text)
            self.config(state=tk.DISABLED)
        def get_content(self):
            return self.get('1.0', tk.END).strip()
        def config(self, *args, **kwargs):
            tk.Text.config(self, *args, **kwargs)