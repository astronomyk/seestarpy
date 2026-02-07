from concurrent.futures import ThreadPoolExecutor
from time import time
from glob import glob
import numpy as np
import cv2
from astropy.io import fits
import astroalign as aa

import matplotlib.pyplot as plt

import fits_header_utils as fhu


def apply_transform_to_frame(args):
    """Apply transformation to a single image"""
    fname, transforms, hdu, target_data = args
    aligned_image, footprint = None, None

    bayer_data = hdu.data.astype(np.uint16)
    bayer_pattern = hdu.header["BAYERPAT"]  # e.g., "GRBG"
    color_code = getattr(cv2, f"COLOR_Bayer{bayer_pattern}2RGB")
    rgb = cv2.cvtColor(bayer_data, color_code)

    if transforms is not None:
        aligned_image, footprint = aa.apply_transform(transforms, rgb, target_data)

    return fname, aligned_image, footprint


def main():
    dir_name = "D:/Seestar/NGC 188_sub"
    # dir_name = "D:/Seestar/IC 434_sub"

    fnames = glob(f"{dir_name}/*.fit")
    n_fnames = len(fnames)
    i = n_fnames // 2

    data_dict = {}

    start = time()

    for fname in fnames:
        with fits.open(fname) as hdul:
            data_dict[fname] = {}
            data_dict[fname]["hdu"] = fits.ImageHDU(header=hdul[0].header,
                                                    data=hdul[0].data)

    print("loading files:", time()-start)
    start = time()

    for fname in fnames:
        image = data_dict[fname]["hdu"].data
        h, w = image.shape
        binned_image = image.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
        sources = aa._find_sources(binned_image)
        data_dict[fname]["sources"] = sources * 2

    print("finding stars:", time()-start)
    start = time()

    target_source = data_dict[fnames[i]]["sources"]
    for fname in fnames:
        transforms, star_coords = None, None
        frame_source = data_dict[fname]["sources"]
        try:
            transforms, star_coords = aa.find_transform(frame_source, target_source)
        except:
            print(f"Found no transform for {fname}")
        data_dict[fname]["transforms"] = transforms
        data_dict[fname]["star_coords"] = star_coords

    print("finding transforms:", time()-start)
    start = time()

    target_data = data_dict[fnames[i]]["hdu"].data
    with ThreadPoolExecutor() as executor:
        args = [(fname,
                 data_dict[fname]["transforms"],
                 data_dict[fname]["hdu"],
                 target_data)
                for fname in fnames]
        results = executor.map(apply_transform_to_frame, args)
        for fname, aligned_image, footprint in results:
            data_dict[fname]["aligned_rgb_image"] = aligned_image
            data_dict[fname]["footprint"] = footprint

    print("applying transforms:", time()-start)
    start = time()

    aligned_rgb_list = [data_dict[fname]["aligned_rgb_image"] for fname in fnames
                        if data_dict[fname]["aligned_rgb_image"] is not None]

    stack_rgb = np.stack(aligned_rgb_list, axis=0)  # (N, H, W)

    sigma_clip = 3.0
    # Optional sigma clipping
    if sigma_clip is not None and stack_rgb.shape[0] > 1:
        mu = np.nanmean(stack_rgb, axis=0)
        sd = np.nanstd(stack_rgb, axis=0)
        lo = mu - sigma_clip * sd
        hi = mu + sigma_clip * sd
        stack_rgb = np.where((stack_rgb < lo) | (stack_rgb > hi), np.nan, stack_rgb)

    # Combine
    combine = "mean"
    if combine == "median":
        stacked_rgb = np.nanmedian(stack_rgb, axis=0)
    elif combine == "mean":
        stacked_rgb = np.nanmean(stack_rgb, axis=0)
    else:
        raise ValueError("combine must be 'median' or 'mean'")

    footprint_list = [data_dict[fname]["footprint"] for fname in fnames
                      if data_dict[fname]["footprint"] is not None]
    stack_footprint = np.stack(footprint_list, axis=0)  # (N, H, W)
    stacked_footprint = np.sum(np.invert(stack_footprint), axis=0)

    print("Stacking images: ", time() - start)

    import sep_pjw as sep
    from astropy.table import Table

    image = np.sum(stacked_rgb, axis=2)
    bkg = sep.Background(image)
    sources = sep.extract(image - bkg.back(), 5 * bkg.globalrms)
    sources.sort(order="flux")
    stars_table = Table(sources)

    stacked_header = fhu.create_stacked_header(data_dict, fnames)
    stacked_hdul = fhu.make_stacked_rgb_fits(stacked_header, stacked_rgb, stacked_footprint, stars_table)

    stacked_hdul.writeto("stacked_rgb.fits", overwrite=True)


    # Normalize to [0, 1] range (simple percentile stretch)
    def simple_normalize(rgb):
        """Stretch each channel to [0, 1] using percentiles"""
        result = np.zeros_like(rgb, dtype=np.float32)
        for i in range(3):
            p1, p99 = np.percentile(rgb[:, :, i], [1, 99])
            result[:, :, i] = np.clip((rgb[:, :, i] - p1) / (p99 - p1), 0, 1)
        return result




    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].imshow(stacked_footprint)
    axes[0].set_title('Reference Image')
    axes[0].axis('off')

    axes[1].imshow(simple_normalize(stacked_rgb))
    axes[1].set_title(f'Stacked ({stack_rgb.shape[0]} images)')
    axes[1].axis('off')

    plt.tight_layout()
    plt.show()



    # img = data_dict[fnames[i]]["aligned_rgb_image"]

    # fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    #
    # axes[0].imshow(simple_normalize(img))
    # axes[0].set_title('Reference Image')
    # axes[0].axis('off')
    #
    # axes[1].imshow(simple_normalize(stacked_rgb))
    # axes[1].set_title(f'Stacked ({stack_rgb.shape[0]} images)')
    # axes[1].axis('off')
    #
    # plt.tight_layout()
    # plt.show()


    # img = data_dict[fnames[i]]["aligned_rgb_image"]
    # img_mean, stacked_mean = np.median(img), np.median(stacked_rgb)
    # img_std, stacked_std = np.std(img), np.std(stacked_rgb)
    #
    # dyn_range = 0.05
    # plt.subplot(121)
    # plt.imshow(img, norm="log",
    #            vmin=img_mean-img_std*dyn_range,
    #            vmax=img_mean+img_std*dyn_range)
    # plt.colorbar()
    # plt.subplot(122)
    # plt.imshow(stacked_rgb, norm="log",
    #            vmin=stacked_mean-stacked_std*dyn_range,
    #            vmax=stacked_mean+stacked_std*dyn_range)
    # plt.colorbar()
    #
    # plt.show()


if __name__ == "__main__":
    main()
