# RV25J_Center

Example of RV25J
https://drive.google.com/file/d/1p3tp_jxk_SooIXAYwciS_K-T6C6_8W42/view?usp=sharing

The RV25J application suite processes land parcel images to extract and verify marker coordinates for cadastre analysis.

Image Preparation: The main GUI (AppRV25J_Center.py) is used to select land images and define a table Region of Interest (ROI), which is clipped and saved as a *_table.jpg file.

OCR Processing: The external script (OCR_RV25j_Process.py) runs Optical Character Recognition (OCR) on the clipped image to extract raw data, clean coordinates, and generate a structured *_OCR.toml file.

Verification: The user verifies and edits the extracted coordinates using OCR_Verify_Edit.py in the GUI, saving changes to a dedicated *_OCRedit.toml file.

Plotting: During verification, the component plots the parcel boundary (*_plot.png) from the edited coordinates to ensure data accuracy.

Geospatial Output: A final script (ParcelCadastre.py) processes all verified *_OCRedit.toml files, transforms coordinates (e.g., Indian 1975 UTM) to WGS84, and outputs the final data as GPKG files

# Integrated TOML Verification and Editing

During the verification process, an integrated TOML editor allows users to review and modify the TOML file directly.
After each update, the parcel is immediately re-plotted for visual confirmation.
![RV25J GUI – Editing Mode](https://raw.githubusercontent.com/phisan-chula/RV25J_Center/main/App_RV25J_GUI_editing.png)

# RV25J Table Selection and Verification – All in One Place

The RV25J Center provides a unified interface where users can select tables, verify OCR results, and visualize parcel geometry seamlessly.
![RV25J GUI](https://raw.githubusercontent.com/phisan-chula/RV25J_Center/main/App_RV25J_GUI.png)
