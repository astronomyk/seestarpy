import numpy as np
from astroalign import register, find_transform, apply_transform
from matplotlib import pyplot as plt
from astropy.io import fits
from pathlib import Path

from glob import glob
from stacking_utils import *

files = glob("D:/Seestar/M 45_sub/*.fit")

groups = group_filenames_by_15min_chunk_ymd(files)
groups = {key: group_files_by_pointing_coords(val) for key, val in groups.items()}
print(groups.keys())
print(groups["20251119-12"])

group_fnames = groups["20251119-12"]["056.70+24.21"]

# 1) Extract starlists once
starlists = extract_starlists_from_fits_group(group_fnames, max_sources=300)

# 2) Choose a reference frame (you decide how)
ref_fn = group_fnames[0]

# 3) Compute transforms to the reference using starlists
xy_only = {fn: arr[:, :2] for fn, arr in starlists.items()}  # if you extracted flux too
transforms = find_transforms_to_reference(xy_only, ref_fn)

# 4) Apply transforms + stack
stacked = apply_transforms_and_stack(
    group_fnames,
    ref_fn,
    transforms,
    combine="median",
    sigma_clip=3.0,
)

img = fits.getdata(group_fnames[0])
img_mean, stacked_mean = np.median(img), np.median(stacked)
img_std, stacked_std = np.std(img), np.std(stacked)

plt.subplot(121)
plt.imshow(img, norm="log",
           vmin=img_mean-img_std*0.03,
           vmax=img_mean+img_std*0.03)
plt.colorbar()
plt.subplot(122)
plt.imshow(stacked, norm="log",
           vmin=stacked_mean-stacked_std*0.03,
           vmax=stacked_mean+stacked_std*0.03)
plt.colorbar()

plt.show()
