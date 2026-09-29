# Third-party software

The **source** version doesn't bundle these. `setup.bat` installs or downloads them.
The **exe releases** (`HeadFocus-Setup-*.exe` and the portable zip) bundle all of them.
The installer itself is made with [Inno Setup](https://jrsoftware.org/isinfo.php), whose
license allows distributing installers built with it, including commercially.

| Component | Used for | License |
|---|---|---|
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) | Face and iris landmark detection | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) |
| MediaPipe Face Landmarker model (`face_landmarker.task`) | The face model, from Google's official model storage | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) |
| [OpenCV](https://github.com/opencv/opencv-python) (`opencv-python`) | Webcam capture and the preview window | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) (OpenCV 4.5+), MIT (the opencv-python packaging) |
| [NumPy](https://numpy.org) | Image arrays (a MediaPipe/OpenCV dependency) | [BSD 3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| [Python](https://www.python.org) runtime (exe only) | Runs the app inside the exe | [PSF License](https://docs.python.org/3/license.html) |
| [PyInstaller](https://pyinstaller.org) bootloader (exe only) | Starts the exe | GPL 2.0 with an exception that allows distributing apps built with it under any license |

The full license texts of everything bundled ship inside the release in the
`licenses\` folder.
