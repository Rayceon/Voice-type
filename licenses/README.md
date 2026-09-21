# Dependency license texts

Voice Type's own code is MIT licensed; see the root `LICENSE`.
The license texts here apply to dependencies under their respective terms.
LGPLv3 incorporates GPLv3, so both complete texts are retained, unchanged.

Retrieved on 2026-09-19 from the Qt project's PySide repository, tag `v6.11.2`:

- [LGPL-3.0-only.txt](https://code.qt.io/cgit/pyside/pyside-setup.git/plain/LICENSES/LGPL-3.0-only.txt?h=v6.11.2)
- [GPL-3.0-only.txt](https://code.qt.io/cgit/pyside/pyside-setup.git/plain/LICENSES/GPL-3.0-only.txt?h=v6.11.2)

## Source entry points for the current local preview

The local Linux preview inspected on this date uses PySide6/Shiboken6 6.11.2.
Its Qt shared libraries span Qt Base, Qt SVG and Qt Wayland; it also contains
ICU and other third-party/system libraries. This is not a complete inventory.

- [PySide/Shiboken 6.11.2 source archives](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/)
- [Qt 6.11.2 module sources](https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/)

These links identify upstream sources; they are not a written source offer or
proof that the exact binary's corresponding-source obligations are satisfied.
Before public binary distribution, identify all bundled components and versions,
retain their copyright/third-party notices, verify the exact matching source and
build materials, and provide compliant ongoing access to those materials.
Recheck the inventory when rebuilding: dependency versions are not pinned here.

The source distribution includes this directory. Desktop bundles copy it into
their resources alongside collected dependency metadata. See [third-party notices](../docs/third-party.md)
for remaining release checks; the current artifacts are local development previews.
