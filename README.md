# Bilibili Draw Pixel Utility

A set of Python scripts to help you play the **[Bilibili Sketching Board](http://live.bilibili.com/pages/1702/pixel-drawing)**.

## Features

* Written in asynchronous structure with asyncio and aiohttp, can support a large number of accounts
* Use cURL format command-line to extract user cookies
* Use WebSocket connection to update sketch data incrementally
* Provide plug-in interface to implement something interesting, e.g., dynamic figure, digital clock. See `clock.py` as a demo.
* Easy-to-use tools to convert images to drawing tasks

## Requirements

* Python 3.6
* pillow
* colormath
* aiohttp>=2.2.0
* pendulum

## Tools

* `generate.py`: generate drawing tasks file for draw_pixel.py and guard.py
* `draw_pixel.py`: draw every pixel of a drawing task in order
* `guard.py`: guard a drawing task with passive and active recovering. The passive recovering compares the sketch board and drawing task at start, recovers the polluted pixels in order. The active recovering watches the region of drawing task, recovers the polluted pixel immediately once it appears
* `process_image.py`: scans a image, converts colors that are not available in palette with the nearest available colors. It is based on LAB color space.
* `merge_tasks.py`: merge and sort multiple task files into a single task file.
* `download.py`: download the current sketch board as a GIF image file
* `record.py`: download and save the sketch board every 3 minutes. It is used to record the drawing process, which can be used to create video later.


## Usage

### Install dependencies

Run following command,

```shell
python3 -m pip install -r requirements.txt
```

### Prepare user cookies file

1. Open Chrome DevTools, switch to the Network tab
2. Draw a arbitrary pixel on the sketch board
3. Locate the POST request named draw and right click the mouse on it
4. Select `Copy` -> `Copy as cURL (bash)`, paste and save the content in a text file, e.g., `users.txt`
5. If you have other accounts, login your account and do step 1-4 again. Save each content in a single line. You can have blank line or add comment line with leading `#`

### Generate task an start drawing

1. Prepare you image with your favorite Image Editor, and save the image as a PNG file, e.g., `foo.png`. If you don't want to include some regions in your image, leave those regions transparent
2. If you are not sure whether this image contains unavailable colors, process your image with command, 

    ```shell
    process_image.py foo.png foo_processed.png
    ```
    
3. Note down the top-left coordinate `(x1, y1)` at where you want to place your image
4. Run following command to generate the task file `mytask.json`,

    ```shell
    generate.py -o mytask.json --pattern foo.png --topleft x1 y1
    ```
    
5. Finally, run following command to start the task,

    ```shell
    guard.py mytask.json users.txt
    ```
