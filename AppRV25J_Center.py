import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pathlib import Path
import time
# NEW: Import subprocess for calling the external OCR script
import subprocess

# NEW: Import TOML parsing library
try:
    import tomllib 
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# Import required components
from ImageSelect import ImageSelect 
from Toml_Verify_Edit import OCRTomlEditor 

# --- Configuration Constants ---
WINDOW_TITLE = "RV25J OCR Center"
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 800
DEFAULT_FONT = ('Tahoma', 10)
LOG_FONT = ('Courier New', 9) 
CONFIG_FILE = "config.toml" 

# --- GLOBAL APPLICATION VARIABLES ---
# This path is used if not found in config.toml
DEFAULT_IMAGE_DIR = r".\NarativasTEST" 

class RV25J_OCR_Center(tk.Tk):
    """
    Main application window for the RV25J OCR Center, integrating all components.
    """
    def __init__(self):
        super().__init__()
        
        # NEW: Initialize config attribute and load config
        self.CONFIG = {}
        self._load_config()
        
        # Use config for initial setup parameters, falling back to defaults
        initial_scale = self.CONFIG.get('RV25J_CENTER', {}).get('view_scale', 0.25)
        # Store the default directory path for use with OCR_All subprocess call
        self.default_dir_str = self.CONFIG.get('RV25J_CENTER', {}).get('default_dir', DEFAULT_IMAGE_DIR)

        self.title(WINDOW_TITLE)
        self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
        
        # --- Style Configuration ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        # Define styles for the specific ttk buttons
        self.style.configure('Yellow.TButton', background='yellow')
        self.style.configure('Red.TButton', background='red') 
        
        self.current_scale = 1.0
        self.current_image_path = tk.StringVar(value="")
        self.image_selector: ImageSelect = None
        self.ocr_editor_panel: OCRTomlEditor = None 
        
        # Dictionary to hold references to zoom buttons
        self.zoom_buttons = {}

        self._create_frames()
        
        # CRITICAL FIX: Create middle frame first to initialize ocr_editor_panel
        self._create_middle_frame() 
        self._create_upper_frame() 
        
        self._create_lower_frame()
        
        self.log_activity("Application started successfully.")
        
        self.log_activity(f"Attempting to load files from default directory: {self.default_dir_str}")
        self.load_file_list(self.default_dir_str)
        
        # Apply initial zoom scale read from config.toml (or 0.25 default)
        self._set_scale(initial_scale) 

        self.log_activity("Ready for file selection.")

    def _load_config(self):
        """
        Reads the config.toml file and stores the content in self.CONFIG.
        """
        if tomllib is None:
            print("ERROR: TOML parser ('tomllib' or 'tomli') not found. Using default settings.")
            return

        config_path = Path(CONFIG_FILE)
        if not config_path.exists():
            print(f"WARNING: Configuration file not found: {CONFIG_FILE}. Using default settings.")
            return
            
        try:
            with open(config_path, 'rb') as f:
                self.CONFIG = tomllib.load(f)
            print(f"INFO: Successfully loaded configuration from {CONFIG_FILE}.")
        except Exception as e:
            print(f"ERROR: Failed to parse {CONFIG_FILE}. Using default settings. Error: {e}")
            self.CONFIG = {}


    # --- Refactored Control Methods ---

    def _handle_ocr_click(self, is_all: bool):
        """Wrapper to safely call OCR method on the panel."""
        if is_all:
             # ONLY call subprocess for OCR_All
             self._run_ocr_all_subprocess()
        # NOTE: Single-file OCR (OCR button) logic is now entirely removed.

    def _handle_save_or_edit_click(self):
        """Wrapper to handle the toggling Save/Edit action on the panel."""
        if self.ocr_editor_panel:
            self.ocr_editor_panel.on_save_or_edit_click()
        else:
            self.log_activity("ERROR: OCR panel is not initialized.")
            
    # --- Frame Creation Methods (Structural) ---
    
    def _create_frames(self):
        """Creates the main structural frames and uses pack for vertical distribution."""
        self.upper_frame = ttk.Frame(self, padding="5 10 5 5", relief=tk.FLAT)
        self.upper_frame.pack(side=tk.TOP, fill=tk.X)
        self.upper_frame.columnconfigure(0, weight=1) 
        self.upper_frame.columnconfigure(1, weight=1)

        self.middle_frame = ttk.Frame(self, padding="5", relief=tk.FLAT)
        self.middle_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.middle_frame.columnconfigure(0, weight=15)
        self.middle_frame.columnconfigure(1, weight=70)
        self.middle_frame.columnconfigure(2, weight=15)
        self.middle_frame.rowconfigure(0, weight=1)

        self.lower_frame = ttk.Frame(self, padding="5", relief=tk.SUNKEN)
        self.lower_frame.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_upper_frame(self):
        """Populates the upper frame with control buttons."""
        left_controls = ttk.Frame(self.upper_frame)
        left_controls.pack(side=tk.LEFT, padx=5)
        
        # RESTORED: Open button
        ttk.Button(left_controls, text="Open...", command=self._open_directory).pack(side=tk.LEFT, padx=5)

        # Scaling buttons
        ttk.Separator(left_controls, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill='y')
        ttk.Label(left_controls, text="Zoom:", font=DEFAULT_FONT).pack(side=tk.LEFT, padx=(0, 5))
        
        # FIX: Using tk.Button for zoom controls to allow relief manipulation
        self.zoom_buttons[1.0] = tk.Button(left_controls, text="1:1", command=lambda: self._set_scale(1.0))
        self.zoom_buttons[0.5] = tk.Button(left_controls, text="1:2", command=lambda: self._set_scale(0.5))
        self.zoom_buttons[0.25] = tk.Button(left_controls, text="1:4", command=lambda: self._set_scale(0.25))

        # Pack and store the zoom buttons
        self.zoom_buttons[1.0].pack(side=tk.LEFT, padx=2)
        self.zoom_buttons[0.5].pack(side=tk.LEFT, padx=2)
        self.zoom_buttons[0.25].pack(side=tk.LEFT, padx=2)

        # OCR and Editing Buttons 
        ttk.Separator(left_controls, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill='y')

        # OCR_All button with Red style (using ttk.Button)
        # Command calls the handler which now runs the subprocess
        ttk.Button(left_controls, 
                   text="OCR_All", 
                   command=lambda: self._handle_ocr_click(is_all=True),
                   style='Red.TButton'
                   ).pack(side=tk.LEFT, padx=2)
        
        # Edit/Save TOML button with Yellow style (using ttk.Button)
        ttk.Button(left_controls, 
                   text="Edit/Save TOML", 
                   command=self._handle_save_or_edit_click,
                   style='Yellow.TButton'
                   ).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(self.upper_frame, text="Quit", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        
    def _set_scale(self, scale):
        """
        Sets the scale, delegates to the ImageSelect component, and updates 
        the visual state (relief) of the zoom buttons (now tk.Button).
        """
        self.current_scale = scale
        
        if self.image_selector:
            self.image_selector.set_scale(scale) 
            self.log_activity(f"Set image scale to {scale:.2f}x.")
            
        # Update button relief for visual feedback
        for zoom_value, button in self.zoom_buttons.items():
            if zoom_value == scale:
                # Set the active button to a 'pressed' or 'sunken' state
                button.config(relief='sunken')
            else:
                # Set inactive buttons back to a 'normal' or 'raised' state
                button.config(relief='raised')

    def _open_directory(self):
        """
        Handles directory selection, defaulting to the path from config or CWD if invalid.
        """
        
        # Use config value if available, fall back to module constant
        initial_dir = self.CONFIG.get('RV25J_CENTER', {}).get('default_dir', DEFAULT_IMAGE_DIR)
        initial_dir = Path(initial_dir) 
        
        # If the configured path is invalid, fall back to the current working directory (CWD)
        if not initial_dir.is_dir():
            initial_dir = Path.cwd()
            self.log_activity(f"WARNING: Configured default directory not found or invalid. Using CWD: {initial_dir.name}")
            
        directory = filedialog.askdirectory(
            title="Select Directory with _RV25J.jpg Files",
            initialdir=str(initial_dir)
        )
        if directory:
            # Update the application's default directory string
            self.default_dir_str = directory
            self.log_activity(f"Selected directory: {directory}")
            self.load_file_list(directory)
            self.log_activity("File list updated.")
        else:
            self.log_activity("Directory selection cancelled.")


    def _create_middle_frame(self):
        """Sets up the three sub-frames in a grid layout."""
        self.left_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.left_subframe.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self._create_file_list(self.left_subframe)

        self.mid_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.mid_subframe.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        self._create_image_display(self.mid_subframe)

        self.right_subframe = ttk.Frame(self.middle_frame, padding="5", relief=tk.RIDGE)
        self.right_subframe.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)
        self._create_ocr_verification_panel(self.right_subframe)

    def _create_file_list(self, parent):
        """Creates the Treeview for the list of folders and files."""
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        
        ttk.Label(parent, text="RV25J Image Files", font=DEFAULT_FONT).grid(row=0, column=0, sticky='w', pady=2)
        
        self.file_list = ttk.Treeview(parent, columns=('Path'), show='tree headings', selectmode='browse')
        self.file_list.heading('#0', text='Full File Path')
        self.file_list.column('Path', width=0, stretch=tk.NO)
        self.file_list.grid(row=1, column=0, sticky='nsew')
        
        yscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.file_list.yview)
        yscroll.grid(row=1, column=1, sticky='ns')
        self.file_list.configure(yscrollcommand=yscroll.set)

        self.file_list.bind('<<TreeviewSelect>>', self._on_file_select)
        
    def _create_image_display(self, parent):
        """Instantiates the ImageSelect component."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.image_selector = ImageSelect(parent, log_callback=self.log_activity, relief=tk.SUNKEN)
        self.image_selector.grid(row=0, column=0, sticky='nsew')

    def _create_ocr_verification_panel(self, parent):
        """Instantiates the new OCR Toml Editor panel."""
        parent.rowconfigure(0, weight=1) 
        parent.columnconfigure(0, weight=1)
        
        panel_container = ttk.Frame(parent)
        panel_container.pack(fill='both', expand=True)
        
        # FIX: Extract and pass COLUMN_SPEC from config
        column_spec = self.CONFIG.get('META', {}).get('COLUMN_SPEC', [])
        
        self.ocr_editor_panel = OCRTomlEditor(
            panel_container, 
            log_callback=self.log_activity, 
            column_spec=column_spec, # Pass the column list
            relief=tk.FLAT
        )
        self.ocr_editor_panel.pack(fill='both', expand=True) 

    def _create_lower_frame(self):
        """Creates the multi-purpose text editor/log box in the lower frame."""
        self.lower_frame.rowconfigure(0, weight=1)
        self.lower_frame.columnconfigure(0, weight=1)
        
        ttk.Label(self.lower_frame, text="Activity Log / Console Output", font=DEFAULT_FONT).grid(row=0, column=0, sticky='w')
        
        self.activity_log = tk.Text(
            self.lower_frame,
            height=6, 
            width=1,  
            state=tk.DISABLED,
            font=LOG_FONT,
            relief=tk.FLAT,
            background='#f0f0f0'
        )
        self.activity_log.grid(row=1, column=0, sticky='nsew', pady=5)
        
        log_scroll = ttk.Scrollbar(self.lower_frame, orient=tk.VERTICAL, command=self.activity_log.yview)
        log_scroll.grid(row=1, column=1, sticky='ns', pady=5)
        self.activity_log.config(yscrollcommand=log_scroll.set)
        
    def _run_ocr_all_subprocess(self):
        """
        Executes OCR_RV25j_Process.py using subprocess.run(), waiting for 
        the process to finish and capturing all output at once.
        """
        script_path = "OCR_RV25j_Process.py"
        folder = self.default_dir_str
        
        if not Path(folder).is_dir():
             messagebox.showerror("OCR Error", f"Folder not found: {folder}. Cannot run OCR_All.")
             self.log_activity(f"FATAL ERROR: Target folder not found: {folder}")
             return

        command = ['python', script_path, folder]
        command_str = ' '.join(command)
        
        self.log_activity(f"Action: Running OCR_All (blocking call): {command_str}")

        try:
            # Use subprocess.run() to block and capture all output upon completion
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False # Do not raise exception on non-zero exit code
            )
            
            # --- Display Captured Output (No real-time text) ---
            if result.stdout:
                self.log_activity("-" * 20 + " SUBPROCESS OUTPUT START " + "-" * 20)
                # Log all output in one block
                self.log_activity(result.stdout.strip())
                self.log_activity("-" * 20 + " SUBPROCESS OUTPUT END " + "-" * 22)
            
            if result.returncode == 0:
                self.log_activity("SUCCESS: OCR_All process finished successfully.")
            else:
                self.log_activity(f"ERROR: OCR_All process failed with return code {result.returncode}.")
                if result.stderr:
                     self.log_activity(f"SUBPROCESS STDERR: {result.stderr.strip()}")
                messagebox.showerror("OCR Error", f"OCR_All process failed. Check Activity Log for details.")
                
        except FileNotFoundError:
            self.log_activity(f"FATAL ERROR: Python or script '{script_path}' not found. Ensure they are in PATH.")
            messagebox.showerror("OCR Error", "Python interpreter or OCR script not found.")
        except Exception as e:
            self.log_activity(f"FATAL ERROR: An unexpected error occurred during subprocess execution: {e}")
            messagebox.showerror("OCR Error", f"Unexpected error during OCR_All: {e}")

        # After OCR_All finishes, we should reload the file list/panels to reflect new files
        self.load_file_list(folder)


    # --- Utility and Logic Methods ---

    def log_activity(self, message):
        """Logs a timestamped message to the activity log text box."""
        timestamp = time.strftime("[%H:%M:%S]")
        log_message = f"{timestamp} {message}\n"
        
        self.activity_log.config(state=tk.NORMAL)
        self.activity_log.insert(tk.END, log_message)
        self.activity_log.config(state=tk.DISABLED)
        self.activity_log.see(tk.END)
        
    def load_file_list(self, base_dir):
        """
        Clears the file list and inserts all file paths found in the base_dir 
        and its subdirectories, filtered by *_RV25J.jpg, as a flat list.
        """
        for item in self.file_list.get_children():
            self.file_list.delete(item)

        root_path = Path(base_dir)
        
        if not root_path.is_dir():
            self.log_activity(f"Error: Directory does not exist or is inaccessible: {root_path}")
            self.file_list.insert('', tk.END, text=f"[Directory Not Found: {root_path}]", open=False)
            return

        found_files = 0
        
        # FIX: os.walk is necessary for deep scan
        for dirpath, _, filenames in os.walk(root_path):
            current_dir = Path(dirpath)
            # Filter for *.jpg extension
            rv25j_files = [f for f in filenames if f.lower().endswith('_rv25j.jpg')]
            
            for filename in rv25j_files:
                file_path = current_dir / filename
                self.file_list.insert('', tk.END, values=(str(file_path),), text=str(file_path))
                found_files += 1

        self.log_activity(f"Finished scanning '{root_path}'. Found {found_files} files.")


    def _on_file_select(self, event):
        """Handles the event when a file/item is selected in the Treeview."""
        selected_item = self.file_list.focus()
        item_data = self.file_list.item(selected_item)
        
        file_path_str = item_data['text']
        
        if not file_path_str or not Path(file_path_str).exists():
            return
            
        file_path = Path(file_path_str)
        file_name = file_path.name
        
        self.current_image_path.set(file_path_str)
        self.log_activity(f"Selected file: {file_name}. Full Path: {file_path_str}.")

        # 1. Derive base name string (everything to the left of '_RV25J')
        base_name_str = file_path.stem
        if base_name_str.lower().endswith('_rv25j'):
            base_name_str = base_name_str[:-6] 

        # 2. Load the selected image into the ImageSelect component
        if self.image_selector:
            self.image_selector.load_image(file_path_str)
        
        # 3. Load the corresponding OCR/TOML files into the verification panel
        if self.ocr_editor_panel:
            self.ocr_editor_panel.load_files(file_path.parent, base_name_str)
        
        # Apply zoom scale from config or default (0.25)
        zoom_scale = self.CONFIG.get('RV25J_CENTER', {}).get('view_scale', 0.25)
        self._set_scale(zoom_scale)


if __name__ == '__main__':
    try:
        app = RV25J_OCR_Center()
        app.mainloop()
    except Exception as e:
        print(f"An error occurred while running the application: {e}")