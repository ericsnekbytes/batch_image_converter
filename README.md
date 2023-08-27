# Batch Image Converter (Tentative Title)

*NOTE: This project is in pre-release, wait for a full release for a better install experience*

Want to easily convert a lot of images to others formats? This project is for you!

## How Does it work?

### Step 1: Pick a folder with some images

<img width="687" alt="image" src="https://github.com/ericsnekbytes/batch_image_converter/assets/104786633/20555dcd-a57e-4647-95fe-3ce29950449d">

Choose what file extensions to search for, and you'll get a list of images scheduled for conversion.

### Step 2: Pick a save/output folder

<img width="603" alt="image" src="https://github.com/ericsnekbytes/batch_image_converter/assets/104786633/cc250c00-2838-49ec-8d8d-e93e0e26df32">

Choose where to save the converted/processed images, and what format(s) to save to. Conflicting filenames
will be resolved automatically by appending "conflicting_name.0001.jpg" number suffixes to the input filename.

### Step 3 (Optional): Add modifiers

<img width="600" alt="image" src="https://github.com/ericsnekbytes/batch_image_converter/assets/104786633/787e1c88-83b4-48e2-82a1-2df1b4084e5e">

Scale your images or add other modifiers (percent scaling is the only modifier currently).

### That's it!

<img width="603" alt="image" src="https://github.com/ericsnekbytes/batch_image_converter/assets/104786633/13954647-602e-4fe8-962e-bb555fbb01a9">

Use the "Start Conversion" button to begin (you'll see a summary screen with all the previous options). When
conversion starts, you'll get a status bar, and a log file with a status for each file.

## Installation

This project is in pre-release, right now you can run from source (with `python -m batch_image_converter`) with
the batch_image_converter folder in your working directory, in an environment with `PySide6` and `pillow`.
Check back later for pre-built binaries.
