# Step 06 — Sentinel-1 Preprocessing and Derived Channels

## Read first

Source section 3 and section 4.4; Steps 01-05.

## Build

Create a configurable, restartable SAR processing DAG: precise orbit when
available, thermal-noise removal, sigma/gamma calibration, optional dB conversion,
optional speckle experiment, terrain correction, invalid-border masking,
reprojection, AOI clipping, and tiling preparation. Use SNAP only behind an
optional CLI adapter where pure Python/GDAL is not reliable; fail with actionable
setup instructions when a required scientific operation is unavailable.

Support VV, VH, dB variants, VV/VH ratio, VV−VH dB, local textures, incidence
angle, land mask, and distance-to-coast/vessel/platform derived channels. Record
formula, units, nodata, CRS, affine transform, source/target resolution/dimensions,
resampler, software versions, parameters and checksums in the processing manifest.
Never overwrite raw data.

## Tests and gates

- Tiny synthetic georeferenced fixtures test calibration/dB guards, channel
  formulas, nodata, clipping/reprojection, deterministic manifests and restart.
- Categorical layers use nearest-neighbour; continuous resampling is justified.
- Optional speckle filtering is off by default and its effect is traceable.
- Scientific steps that cannot be correctly performed by available libraries are
  explicit adapter boundaries, never approximated silently.
