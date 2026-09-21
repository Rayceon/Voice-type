# Third-party components

Voice Type's own code is MIT licensed. That license does not replace the licenses
of its dependencies. The application does not modify the dependencies below.

| Component | Upstream / license |
| --- | --- |
| Python | https://www.python.org/ — PSF and bundled component licenses |
| PyInstaller bootloader | https://pyinstaller.org/ — GPL with the PyInstaller distribution exception; see bundled COPYING.txt |
| PySide6, Shiboken6, Qt | https://code.qt.io/ — LGPLv3/GPL/commercial, plus Qt third-party notices |
| pynput, python-xlib | https://github.com/moses-palmer/pynput / https://github.com/python-xlib/python-xlib — LGPLv3 / LGPLv2.1 |
| python-sounddevice, PortAudio | https://github.com/spatialaudio/python-sounddevice / https://www.portaudio.com/ — MIT |
| NumPy | https://github.com/numpy/numpy — BSD, plus bundled numeric library licenses |
| soxr, libsoxr | https://github.com/dofuuz/python-soxr / https://sourceforge.net/projects/soxr/ — LGPLv2.1, plus bundled notices |
| websocket-client | https://github.com/websocket-client/websocket-client — Apache-2.0 |
| certifi | https://github.com/certifi/python-certifi — MPL-2.0 |
| platformdirs, keyring | https://github.com/platformdirs/platformdirs / https://github.com/jaraco/keyring — MIT |
| dbus-next | https://github.com/altdesktop/python-dbus-next — MIT |

Builds preserve available installed distribution metadata and license files under
the bundle's `_internal` directory (macOS uses its bundle Resources/Frameworks).
Python's original license is collected from the build interpreter's installation
prefix or standard-library directory into `licenses/python`; the build fails if
neither contains it. PyInstaller's metadata includes its bootloader license and
distribution exception. These checks do not certify the entire bundle's licensing.
Verbatim LGPLv3 and GPLv3 texts are included in `licenses/`; LGPLv3 incorporates
GPLv3. Their upstream provenance and version-specific source entry points are in
`licenses/README.md`. These are dependency notices, not a change to Voice Type's
own MIT license, and do not replace corresponding source or third-party notices.
Some binary wheels (notably Qt) omit full license/source materials; those must be
obtained from the exact upstream release before a public binary release.
Dynamic libraries are separate files so users can replace compatible LGPL
libraries; no rule in this project prohibits modification or reverse engineering
for debugging such modifications. The source package and build specification
provide the application code and rebuild instructions.

Before distributing a binary publicly, review the exact platform artifact's full
dependency inventory, supply corresponding LGPL sources or a compliant source
offer, retain all notices, and check any extra system libraries bundled by the
packager. These preview builds have not completed that release review, signing,
or notarization. MIT selection alone does not establish binary release readiness.
