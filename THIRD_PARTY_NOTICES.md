# Third-party components

Luma core is GPL-3.0-or-later. The independent collector integration in `collector/` is GPL-2.0-only. These notices do not grant rights to user media or collected posts.

The core uses Electron (MIT), React (MIT), Lucide (ISC), flag-icons (MIT), Python (PSF), Pillow (HPND), NumPy (BSD), ONNX Runtime (MIT), tokenizers and RapidOCR (Apache-2.0), Shapely (BSD) and its GEOS DLLs (LGPL-2.1). Original license and NOTICE files and a version inventory are in `resources/licenses`. Electron's Chromium notices are retained too. PyInstaller retains its bootloader bundling exception.

The public core EXE excludes gallery-dl and imageio-ffmpeg. The independent collector EXE excludes gallery-dl and its HTTP dependencies. On first use, the collector downloads the exact universal wheels in `collector/engine-lock.json` directly from official PyPI hosting and checks their sizes and SHA-256 hashes. They remain under their original licenses. No system Python or pip is required. Network access is needed for this first component installation.

FFmpeg 7.1.5 is an independent executable built from upstream commit `3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587`. `tools/build_ffmpeg.sh` disables GPL, nonfree, version3 and autodetected dependencies. The release includes its corresponding source, LGPL-2.1 text, configuration and build script. The build sets VERSION to 7.1.5. It does not use the GPL build supplied by imageio-ffmpeg. Windows Schannel provides HTTPS. FFmpeg and GEOS can be replaced in the installed or expanded application with compatible builds; reverse engineering to debug those modifications is permitted.

Chinese-CLIP is an optional model downloaded separately from Xenova/chinese-clip-vit-base-patch16, based on OFA-Sys/Chinese-CLIP. Luma pins the revision and verifies the model weight hash. The original model card and license apply. Images are processed locally, without cloud inference uploads. Model weights are not included in the source archive or EXE.

Each release supplies Luma source and a separate third-party source archive with FFmpeg, GEOS, Shapely and PyInstaller sources. See `docs/SOURCE_CODE.md` and `docs/BUILDING.md` for rebuild instructions. The Windows executables are currently unsigned.
