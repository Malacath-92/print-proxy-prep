# print-proxy-prep
Crop bleed edges from proxy images and make PDFs for at-home printing.

![image](https://user-images.githubusercontent.com/103437609/203212263-1a029874-3611-4daf-8ac5-e1d23b429db6.png)

# Installation

## Tl;Dr
- Install latest Python, make sure to add to `PATH`
- Clone the repo
- Run `1_SETUP.bat`
- Run `2_RUN.vbs`

## Detailed
You're gonna need <a href="https://www.python.org/downloads/">Python</a>, I'd say whatever the latest version is, should work.
When installing, make sure to add Python to `PATH`. ![image](https://user-images.githubusercontent.com/103437609/203196002-f04b0c0d-cb2e-4154-ba90-f2f9578ced95.png)

With Python installed, go ahead and download the zip and unzip it wherever you like.
![image](https://user-images.githubusercontent.com/103437609/203219985-019cea6e-2a85-4ea8-ba90-b96e7665eae7.png)

There is a batch script to help with installation if you're not savvy with Python, go ahead and run 1_SETUP.bat and it should make a folder called `images` and one called `venv`. Then, it will use pip to install the dependencies from `requirements.txt` into that virtual environment.

Then, you can run main.py from the command line like `venv\scripts\python main.py`, or `2_RUN.vbs` that you can just click and it will pop up the GUI.

# Running the Program
![image](https://user-images.githubusercontent.com/103437609/203212112-50db47df-0a4e-4bf2-9c59-a8554f521b7c.png)

First, throw some images with bleed edge in the `images` folder. Note that images starting with `__` will not be visible in the program. Then, when you opem main.py or hit the `Run Cropper` button from the GUI, it will go through all the images and crop them.

## Card Grid
The left half of the window contains a grid of all cards you placed in the `images` folder. Below each image is an text input field and a +/-, use these to adjust how many copies for each card you want. On the top you have global controls to +/- all cards or reset them back to 1.

## Print Preview
On the top-left you can switch over to the `Preview`, which shows you a preview of the printed page. It should update automatically when you change printing settings on the right.

## Options
The right panel contains all the options for printing. Most are self-explanatory, but the ones that are not will be outlined here.

### Extended Guides
Extends the guides for the cards on the edges of the layout to the very edge of the page, will require a tiny bit more ink to print but makes cutting much easier.

### Bleed Edge
Instead of printing cards perfectly cropped to card size will leave a small amount of bleed edge. This emulates the real printing process and thus makes it easier to cut without having adjacent cards visible on slight miscuts at the cost of more ink usage.

### Enable Backside
Adds a backside to each image, which means when printing each other page will automatically be filled with the corresponding backsides for each image. This allows for double-sided cards, different card backs, etc.

The default backside is `__back.png`, if that file is not available a question mark will be shown instead. To change the default just click on the `Default` button and browse to the image you want.

To change the backside for an individual card, click on the backside for that card in the card grid and brows to the image you want.

In some cases one can't use Duplex Printing, either because the printer doesn't support it or the print medium is too thick. In those cases you'll have to manually turn the page between front- and backside prints. For many printers this will result in a slight offset between the two sides that is more or less consistent. Do a test print to measure this difference and insert it into the `Offset` field.

### Allow Precropped
In some cases you may find yourself having card images that don't have a bleed edge. In those cases, enable this option and place your images into the `images/cropped` folder. The program will automatically add a black bleed edge so that all features of the program work as intended.

### Vibrance Bump
When printing onto holographic paper/sticker/cardstock enable this setting to get a more vibrant looking result.

## Render Document

When you're done getting your print setup, hit this button in the top right and it will make your PDF and open it up for you. Hopefully you can handle yourself from there.

# SOME NOTES:
- If you need support for a new feature, please open an Issue.
- The program will automatically save if you close the window. It will not save if it crashes! The data is stored in print.json.
- image.cache if a file that is made that stores the data for the thumbnails.
- If the program crashes on startup first try to delete these two files, if that doesn't do it open an issue.
- When opening an issue to report a bug, please attach a zip file containing your `images` folder and your `print.json` and `img.cache`.
