import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pathlib import Path
import time
import subprocess

# --- TOML Library Import ---
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# --- Custom Component Imports ---
# Ensure ImageSelect.py and Toml_Verify_Edit.py are in the same directory
from ImageSelect import ImageSelect 
from Toml_Verify_Edit import OCRTomlEditor 

# --- Configuration Constants ---
WINDOW_TITLE = "RV25J OCR Center"
DEFAULT_WIDTH = 1300
DEFAULT_HEIGHT = 850
DEFAULT_FONT = ('Tahoma', 10)
LOG_FONT = ('Courier New', 9)
CONFIG_FILE = "config.toml"

# Default fallback if config is missing
DEFAULT_IMAGE_DIR = r".\RV25J_L1L2"

class RV25J_OCR_Center(tk.Tk):
    """
    Main application window for the RV25J OCR Center.
    Integrates File List, Image Viewer, and TOML Editor.
    """
    def __init__(self):
        super().__init__()
        
        # 1. Load Configuration
        self.CONFIG = {}
        self._load_config()
        
        # 2. Setup Defaults based on Config
        initial_scale = self.CONFIG.get('RV25J_CENTER', {}).get('view_scale', 0.25)
        self.default_dir_str = self.CONFIG.get('RV25J_CENTER', {}).get('default_dir', DEFAULT_IMAGE_DIR)

        # 3. Setup Main Window
        self.title(WINDOW_TITLE)
        self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
        
        # 4. Style Configuration
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('Yellow.TButton', background='yellow')
        self.style.configure('Red.TButton', background='red', foreground='white') 
        
        # 5. State Variables
        self.current_scale = 1.0
        self.current_image_path = tk.StringVar(value="")
        self.zoom_buttons = {}

        # 6. Build UI Layout
        self._create_frames()
        self._create_middle_frame() # Must be created before Upper to init panels
        self._create_upper_frame() 
        self._create_lower_frame()
        
        self.log_activity("Application started successfully.")
        
        # 7. Initial Load
        self.log_activity(f"Attempting to load files from: {self.default_dir_str}")
        self.load_file_list(self.default_dir_str)
        self._set_scale(initial_scale)

    def _load_config(self):
        """Reads config.toml."""
        if tomllib is None:
            print("ERROR: TOML parser not found. Using defaults.")
            return

        config_path = Path(CONFIG_FILE)
        if not config_path.exists():
            print(f"WARNING: {CONFIG_FILE} not found. Using defaults.")
            return
            
        try:
            with open(config_path, 'rb') as f:
                self.CONFIG = tomllib.load(f)
            print(f"INFO: Loaded configuration from {CONFIG_FILE}.")
        except Exception as e:
            print(f"ERROR: Failed to parse config.toml: {e}")

    # ========================================================
    # UI CONSTRUCTION
    # ========================================================

    def _create_frames(self):
        """Top-level layout frames."""
        self.upper_frame = ttk.Frame(self, padding="5 10 5 5", relief=tk.FLAT)
        self.upper_frame.pack(side=tk.TOP, fill=tk.X)

        self.middle_frame = ttk.Frame(self, padding="5", relief=tk.FLAT)
        self.middle_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.lower_frame = ttk.Frame(self, padding="5", relief=tk.SUNKEN)
        self.lower_frame.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_upper_frame(self):
        """Controls: Open, Zoom, OCR, Save."""
        # -- Left Controls Container --
        left_controls = ttk.Frame(self.upper_frame)
        left_controls.pack(side=tk.LEFT, padx=5)
        
        # Open Button
        ttk.Button(left_controls, text="Open...", command=self._open_directory).pack(side=tk.LEFT, padx=5)

        # Separator
        ttk.Separator(left_controls, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill='y')
        ttk.Label(left_controls, text="Zoom:", font=DEFAULT_FONT).pack(side=tk.LEFT, padx=(0, 5))
        
        # Zoom Buttons (using tk.Button for relief control)
        self.zoom_buttons[1.0] = tk.Button(left_controls, text="1:1", command=lambda: self._set_scale(1.0))
        self.zoom_buttons[0.5] = tk.Button(left_controls, text="1:2", command=lambda: self._set_scale(0.5))
        self.zoom_buttons[0.25] = tk.Button(left_controls, text="1:4", command=lambda: self._set_scale(0.25))

        self.zoom_buttons[1.0].pack(side=tk.LEFT, padx=2)
        self.zoom_buttons[0.5].pack(side=tk.LEFT, padx=2)
        self.zoom_buttons[0.25].pack(side=tk.LEFT, padx=2)

        # Separator
        ttk.Separator(left_controls, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill='y')

        # OCR All Button
        ttk.Button(left_controls, 
                   text="OCR_All", 
                   command=self._run_ocr_all_subprocess,
                   style='Red.TButton'
                   ).pack(side=tk.LEFT, padx=2)
        
        # Edit/Save Button
        ttk.Button(left_controls, 
                   text="Edit/Save TOML", 
                   command=self._handle_save_or_edit_click,
                   style='Yellow.TButton'
                   ).pack(side=tk.LEFT, padx=10)
        
        # Quit Button
        ttk.Button(self.upper_frame, text="Quit", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _create_middle_frame(self):
        """3-Column Layout: List | Image | Editor."""
        # Configure Grid Weights
        self.middle_frame.columnconfigure(0, weight=15) # File List
        self.middle_frame.columnconfigure(1, weight=65) # Image
        self.middle_frame.columnconfigure(2, weight=20) # Editor
        self.middle_frame.rowconfigure(0, weight=1)

        # 1. Left Subframe (File List)
        self.left_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.left_subframe.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self._create_file_list(self.left_subframe)

        # 2. Middle Subframe (Image)
        self.mid_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.mid_subframe.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        self._create_image_display(self.mid_subframe)

        # 3. Right Subframe (Editor)
        self.right_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.right_subframe.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)
        self._create_ocr_verification_panel(self.right_subframe)

    def _create_file_list(self, parent):
        """File List with Vertical AND Horizontal Scrollbars."""
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        
        ttk.Label(parent, text="RV25J Image Files", font=DEFAULT_FONT).grid(row=0, column=0, sticky='w', pady=2)
        
        # Treeview setup
        self.file_list = ttk.Treeview(parent, columns=('Path'), show='tree', selectmode='browse')
        self.file_list.heading('#0', text='File List')
        self.file_list.column('#0', width=250) 
        # Hidden column to store actual full path
        self.file_list.column('Path', width=0, stretch=tk.NO) 
        
        # Vertical Scrollbar
        yscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=yscroll.set)

        # Horizontal Scrollbar
        xscroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.file_list.xview)
        self.file_list.configure(xscrollcommand=xscroll.set)

        # Grid placement
        self.file_list.grid(row=1, column=0, sticky='nsew')
        yscroll.grid(row=1, column=1, sticky='ns')
        xscroll.grid(row=2, column=0, sticky='ew')

        # Bind selection event
        self.file_list.bind('<<TreeviewSelect>>', self._on_file_select)

    def _create_image_display(self, parent):
        """Embeds ImageSelect component."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.image_selector = ImageSelect(parent, log_callback=self.log_activity, relief=tk.SUNKEN)
        self.image_selector.grid(row=0, column=0, sticky='nsew')

    def _create_ocr_verification_panel(self, parent):
        """Embeds OCRTomlEditor component."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        
        panel_container = ttk.Frame(parent)
        panel_container.pack(fill='both', expand=True)
        
        # Get column spec from config (e.g. ["MRK_DOL", "NORTHING", "EASTING"])
        column_spec = self.CONFIG.get('META', {}).get('COLUMN_SPEC', [])
        
        self.ocr_editor_panel = OCRTomlEditor(
            panel_container, 
            log_callback=self.log_activity, 
            column_spec=column_spec,
            relief=tk.FLAT
        )
        self.ocr_editor_panel.pack(fill='both', expand=True)

    def _create_lower_frame(self):
        """Activity Log."""
        self.lower_frame.rowconfigure(0, weight=1)
        self.lower_frame.columnconfigure(0, weight=1)
        
        ttk.Label(self.lower_frame, text="Activity Log / Console Output", font=DEFAULT_FONT).grid(row=0, column=0, sticky='w')
        
        self.activity_log = tk.Text(
            self.lower_frame, height=6, width=1, state=tk.DISABLED,
            font=LOG_FONT, relief=tk.FLAT, background='#f0f0f0'
        )
        self.activity_log.grid(row=1, column=0, sticky='nsew', pady=5)
        
        log_scroll = ttk.Scrollbar(self.lower_frame, orient=tk.VERTICAL, command=self.activity_log.yview)
        log_scroll.grid(row=1, column=1, sticky='ns', pady=5)
        self.activity_log.config(yscrollcommand=log_scroll.set)

    # ========================================================
    # LOGIC & EVENTS
    # ========================================================

    def load_file_list(self, base_dir):
        """
        Scans dir for *_RV25J.jpg, SORTS them, and adds NUMBERING.
        """
        # Clear existing
        for item in self.file_list.get_children():
            self.file_list.delete(item)

        root_path = Path(base_dir)
        if not root_path.is_dir():
            self.log_activity(f"Error: Invalid directory: {root_path}")
            return

        all_rv25j_files = []
        
        # 1. Scan recursively
        for dirpath, _, filenames in os.walk(root_path):
            current_dir = Path(dirpath)
            for f in filenames:
                if f.lower().endswith('_rv25j.jpg'):
                    all_rv25j_files.append(current_dir / f)

        # 2. Sort Alphabetically
        all_rv25j_files.sort()

        # 3. Insert with Numbering [1], [2]...
        for idx, file_path in enumerate(all_rv25j_files, start=1):
            # Display: [1] C:\Path\...\Img_RV25J.jpg
            display_text = f"[{idx}] {file_path}"
            # Values: Clean path (hidden)
            self.file_list.insert('', tk.END, text=display_text, values=(str(file_path),))

        self.log_activity(f"Scanned '{root_path}'. Found {len(all_rv25j_files)} files (Sorted & Numbered).")

    def _on_file_select(self, event):
        """Handles selection from the Treeview."""
        selected_item = self.file_list.focus()
        if not selected_item: return
        
        item_data = self.file_list.item(selected_item)
        
        # EXTRACT PATH FROM HIDDEN VALUE
        if item_data['values']:
            file_path_str = item_data['values'][0]
        else:
            file_path_str = item_data['text'] # Fallback
            
        path_obj = Path(file_path_str)
        if not path_obj.exists():
            self.log_activity(f"Error: File not found {file_path_str}")
            return
            
        self.current_image_path.set(file_path_str)
        self.log_activity(f"Selected: {path_obj.name}")

        # 1. Determine Base Name (remove _RV25J suffix)
        base_name_str = path_obj.stem
        if base_name_str.lower().endswith('_rv25j'):
            base_name_str = base_name_str[:-6]

        # 2. Load Image
        if self.image_selector:
            self.image_selector.load_image(file_path_str)
        
        # 3. Load TOML Data
        if self.ocr_editor_panel:
            self.ocr_editor_panel.load_files(path_obj.parent, base_name_str)
        
        # 4. Apply Scale
        zoom_scale = self.CONFIG.get('RV25J_CENTER', {}).get('view_scale', 0.25)
        self._set_scale(zoom_scale)

    def _run_ocr_all_subprocess(self):
        """Runs the external OCR script."""
        script_path = "OCR_RV25j_Process.py"
        folder = self.default_dir_str
        
        if not Path(folder).is_dir():
             messagebox.showerror("OCR Error", f"Folder invalid: {folder}")
             return

        command = ['python', script_path, folder]
        self.log_activity(f"Running OCR: {' '.join(command)}")

        try:
            # Blocking call - waits for script to finish
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            
            if result.stdout:
                self.log_activity("--- PROCESS OUTPUT ---")
                self.log_activity(result.stdout.strip())
                self.log_activity("----------------------")
            
            if result.returncode == 0:
                self.log_activity("OCR Process Completed Successfully.")
                # Refresh file list/editor in case files changed
                self.load_file_list(folder)
            else:
                self.log_activity(f"OCR Failed (Code {result.returncode})")
                if result.stderr:
                    self.log_activity(f"STDERR: {result.stderr.strip()}")
                messagebox.showerror("OCR Failed", "Check log for details.")
                
        except Exception as e:
            self.log_activity(f"Subprocess Error: {e}")
            messagebox.showerror("Execution Error", str(e))

    def _open_directory(self):
        """Folder picker dialog."""
        initial_dir = Path(self.default_dir_str)
        if not initial_dir.exists(): initial_dir = Path.cwd()
            
        directory = filedialog.askdirectory(
            title="Select Directory with _RV25J.jpg Files",
            initialdir=str(initial_dir)
        )
        if directory:
            self.default_dir_str = directory
            self.log_activity(f"Directory changed to: {directory}")
            self.load_file_list(directory)

    def _set_scale(self, scale):
        """Updates zoom level and button visuals."""
        self.current_scale = scale
        if self.image_selector:
            self.image_selector.set_scale(scale)
            
        for val, btn in self.zoom_buttons.items():
            btn.config(relief='sunken' if val == scale else 'raised')

    def _handle_save_or_edit_click(self):
        """Delegates save/edit to the editor panel."""
        if self.ocr_editor_panel:
            self.ocr_editor_panel.on_save_or_edit_click()

    def log_activity(self, message):
        """Appends text to the log window."""
        ts = time.strftime("[%H:%M:%S]")
        self.activity_log.config(state=tk.NORMAL)
        self.activity_log.insert(tk.END, f"{ts} {message}\n")
        self.activity_log.config(state=tk.DISABLED)
        self.activity_log.see(tk.END)

if __name__ == '__main__':
    try:
        app = RV25J_OCR_Center()
        app.mainloop()
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")