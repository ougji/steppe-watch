# Your first session

Goal: run a working demo, understand one part of it, and publish the first repository.

## 1. Open the folder

Extract this ZIP. Open the `steppe-watch` folder in VS Code, then choose **Terminal → New Terminal**. The terminal should be in the folder containing `app.py` and `requirements.txt`.

You need Python 3.10 or newer. If Python is not installed, get it from [python.org](https://www.python.org/downloads/), enable the installer option to add Python to PATH, then reopen VS Code. See the README for an optional virtual environment setup.

## 2. Run it

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL shown in the terminal if the browser does not open automatically. The app starts with synthetic example images.

## 3. Understand one feature

Try difference thresholds **0**, **35** and **255**. What changes on the orange overlay? At 255, no pixel can pass the strict greater-than test.

Open `change_watch/core.py`. Find:

```python
candidate = (score > threshold) & valid
```

Explain how this line combines the difference threshold with usable pixels. This version has no trained ML model; it establishes a comparison baseline.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## 4. Publish the first version

On [GitHub](https://github.com/new), create an empty public repository called `steppe-watch`. GitHub will display its exact repository URL and commands.

In the project terminal:

```bash
git init
git add .
git commit -m "Add reproducible RGB change detection baseline"
git branch -M main
```

Add the remote using the URL GitHub gives you, then push:

```bash
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

Replace `YOUR_REPOSITORY_URL` with the actual HTTPS URL. If Git asks for your name/email, follow its displayed configuration instructions. If Git is missing, install it from [git-scm.com](https://git-scm.com/downloads).

## 5. The next session

Pick one real location and obtain two comparable, permitted images. Record the source and dates in `DATA_NOTES.md`. Run the baseline, inspect the errors, and use those observations to choose your first improvement.

Tonight is complete when the demo runs, you understand the threshold, and the repository is online.
