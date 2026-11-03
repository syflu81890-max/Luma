#!/usr/bin/env bash
# Build an independent LGPL FFmpeg executable; never use the imageio wheel's GPL build.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
commit=3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587 # upstream n7.1.5
work="$root/.tools/ffmpeg-build"
out="$root/vendor/ffmpeg"
mkdir -p "$work" "$out" "$root/third-party-sources"
if [[ ! -f "$work/source.tar.gz" ]]; then
  curl --fail --location --retry 3 "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/$commit" -o "$work/source.tar.gz"
fi
tar -xzf "$work/source.tar.gz" -C "$work"
cp "$work/source.tar.gz" "$root/third-party-sources/ffmpeg-$commit.tar.gz"
cd "$work/FFmpeg-$commit"
printf '7.1.5\n' > VERSION
./configure --target-os=mingw32 --arch=x86_64 \
  --cross-prefix=x86_64-w64-mingw32- --prefix="$work/install" \
  --disable-autodetect --disable-gpl --disable-nonfree --disable-version3 \
  --disable-doc --disable-debug --disable-ffplay --disable-ffprobe \
  --disable-x86asm --enable-schannel --enable-static --disable-shared \
  --extra-ldflags='-static-libgcc -static'
make -j"$(nproc)" ffmpeg.exe
cp ffmpeg.exe "$out/ffmpeg.exe"
cp COPYING.LGPLv2.1 LICENSE.md "$out/"
cp config.h config_components.h ffbuild/config.mak "$out/"
cp "$root/tools/build_ffmpeg.sh" "$out/BUILD.sh"
printf '%s\n' "$commit" > "$out/UPSTREAM_COMMIT"
if grep -q '^#define CONFIG_GPL 1\|^#define CONFIG_NONFREE 1\|^#define CONFIG_VERSION3 1' config.h; then
  echo 'Unexpected FFmpeg license configuration' >&2; exit 1
fi
sha256sum "$out/ffmpeg.exe" "$root/third-party-sources/ffmpeg-$commit.tar.gz" > "$out/SHA256SUMS"
