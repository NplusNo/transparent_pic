# Transparent Pic 🖼️

## Project Description
Transparent Pic is an image processing tool that allows you to remove backgrounds from images, converting them to transparent PNG files with ease.

## Features
- Background removal
- Conversion of images to transparent PNG files
- Simple and user-friendly interface

## Requirements
- Python 3.8+
- Required libraries (see `requirements.txt`)

## Installation
1. Clone the repository:
```bash
git clone https://github.com/NplusNo/transparent_pic.git
cd transparent_pic
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage
```python
# Example code to use the tool
from transparent_pic import remove_background

# Make image transparent
transparent_image = remove_background('input_image.jpg')
transparent_image.save('output_image.png')
```

## Technologies
- Python
- Image processing libraries

## License

MIT License

Copyright (c) 2024 NplusNo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing
Pull Requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## Contact
- GitHub: [NplusNo](https://github.com/NplusNo)
- X (Twitter): [@nplusno](https://x.com/nplusno)
- Project Link: [transparent_pic](https://github.com/NplusNo/transparent_pic)
