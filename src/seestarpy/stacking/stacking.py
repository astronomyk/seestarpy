"""
Astronomical image stacking module for Seestar telescope FITS files.

This module provides classes for loading, aligning, and stacking astronomical
images captured by Seestar telescopes.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple, Union
import warnings

import numpy as np
import cv2
from astropy.io import fits
from astropy.table import Table
import astroalign as aa

try:
    import sep_pjw as sep
except ImportError:
    import sep

try:
    import fits_header_utils as fhu
    HAS_FHU = True
except ImportError:
    HAS_FHU = False
    warnings.warn("fits_header_utils not available. Some header functionality will be limited.")


class RawFrame:
    """
    Represents a single raw FITS frame from a Seestar telescope.
    
    Attributes:
        filepath: Path to the FITS file
        hdu: FITS ImageHDU containing header and data
        sources: Detected star positions for alignment
        transforms: Transformation parameters for alignment
        star_coords: Matched star coordinates
        aligned_rgb_image: RGB image after alignment
        footprint: Boolean mask indicating valid pixels after alignment
    """
    
    def __init__(self, filepath: Union[str, Path], lazy_load: bool = False):
        """
        Initialize a RawFrame from a FITS file.

        Args:
            filepath: Path to the FITS file
            lazy_load: If True, defer loading until needed (faster initialization)
        """
        self.filepath = Path(filepath)
        self.hdu: Optional[fits.ImageHDU] = None
        self.sources: Optional[np.ndarray] = None
        self.transforms: Optional[aa.SimilarityTransform] = None
        self.star_coords: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self.aligned_rgb_image: Optional[np.ndarray] = None
        self.footprint: Optional[np.ndarray] = None

        if not lazy_load:
            self._load_fits()

    def _ensure_loaded(self) -> None:
        """Ensure FITS file is loaded."""
        if self.hdu is None:
            self._load_fits()

    def _load_fits(self) -> None:
        """Load FITS file data and header."""
        with fits.open(self.filepath) as hdul:
            self.hdu = fits.ImageHDU(
                header=hdul[0].header,
                data=hdul[0].data
            )

    def detect_sources(self, binning: int = 2) -> np.ndarray:
        """
        Detect star sources in the frame for alignment.

        Args:
            binning: Binning factor to speed up source detection

        Returns:
            Array of detected source positions
        """
        self._ensure_loaded()
        image = self.hdu.data
        h, w = image.shape

        # Bin the image to speed up source detection
        binned_image = image.reshape(
            h // binning, binning,
            w // binning, binning
        ).mean(axis=(1, 3))

        # Find sources in binned image
        sources = aa._find_sources(binned_image)

        # Scale back to original coordinates
        self.sources = sources * binning
        return self.sources

    def find_transform(self, target_sources: np.ndarray) -> bool:
        """
        Find transformation to align this frame to target sources.

        Args:
            target_sources: Source positions in the target frame

        Returns:
            True if transform was found, False otherwise
        """
        try:
            self.transforms, self.star_coords = aa.find_transform(
                self.sources, target_sources
            )
            return True
        except Exception as e:
            warnings.warn(f"Could not find transform for {self.filepath.name}: {e}")
            self.transforms = None
            self.star_coords = None
            return False

    def apply_transform(self, target_data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Apply transformation to convert Bayer data to aligned RGB.

        Args:
            target_data: Raw Bayer data from target frame for alignment

        Returns:
            Tuple of (aligned_rgb_image, footprint)
        """
        # Convert Bayer pattern to RGB
        bayer_data = self.hdu.data.astype(np.uint16)
        bayer_pattern = self.hdu.header["BAYERPAT"]  # e.g., "GRBG"
        color_code = getattr(cv2, f"COLOR_Bayer{bayer_pattern}2RGB")
        rgb = cv2.cvtColor(bayer_data, color_code)

        # Apply alignment transform if available
        if self.transforms is not None:
            self.aligned_rgb_image, self.footprint = aa.apply_transform(
                self.transforms, rgb, target_data
            )
        else:
            # No transform available - use original RGB
            self.aligned_rgb_image = rgb
            self.footprint = np.ones(rgb.shape[:2], dtype=bool)

        return self.aligned_rgb_image, self.footprint

    @property
    def is_aligned(self) -> bool:
        """Check if frame has been successfully aligned."""
        return self.aligned_rgb_image is not None


class FrameCollection:
    """
    Collection of RawFrame objects for stacking operations.

    Attributes:
        frames: List of RawFrame objects
        target_index: Index of the reference frame for alignment
        stacked_rgb: Stacked RGB image
        stacked_footprint: Combined footprint mask
        stacked_header: Combined FITS header
    """

    def __init__(self, filepaths: List[Union[str, Path]], lazy_load: bool = True):
        """
        Initialize a FrameCollection from a list of FITS files.

        Args:
            filepaths: List of paths to FITS files
            lazy_load: If True, defer loading FITS files (faster initialization)
        """
        self.frames = [RawFrame(fp, lazy_load=lazy_load) for fp in filepaths]
        self.target_index = len(self.frames) // 2  # Use middle frame as reference
        self.stacked_rgb: Optional[np.ndarray] = None
        self.stacked_footprint: Optional[np.ndarray] = None
        self.stacked_header: Optional[fits.Header] = None
        self._stars_table: Optional[Table] = None

        # Ensure all frames are loaded (can be done in parallel)
        if lazy_load:
            self._load_all_fits()

    @classmethod
    def from_directory(cls, directory: Union[str, Path], pattern: str = "*.fit", lazy_load: bool = True):
        """
        Create a FrameCollection from all FITS files in a directory.

        Args:
            directory: Path to directory containing FITS files
            pattern: Glob pattern for file matching
            lazy_load: If True, defer loading FITS files

        Returns:
            FrameCollection instance
        """
        directory = Path(directory)
        filepaths = sorted(directory.glob(pattern))

        if not filepaths:
            raise ValueError(f"No files matching '{pattern}' found in {directory}")

        return cls(filepaths, lazy_load=lazy_load)

    def _load_all_fits(self, n_workers: Optional[int] = None) -> None:
        """Load all FITS files in parallel."""
        def load_fits_static(args):
            frame_idx, filepath = args
            with fits.open(filepath) as hdul:
                hdu = fits.ImageHDU(
                    header=hdul[0].header,
                    data=hdul[0].data
                )
            return frame_idx, hdu

        args_list = [(i, frame.filepath) for i, frame in enumerate(self.frames)]

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = executor.map(load_fits_static, args_list)
            for frame_idx, hdu in results:
                self.frames[frame_idx].hdu = hdu

    def detect_all_sources(self, binning: int = 2, parallel: bool = False, n_workers: Optional[int] = None) -> None:
        """
        Detect sources in all frames.

        Args:
            binning: Binning factor for source detection
            parallel: Use parallel processing (usually not needed, detection is fast)
            n_workers: Number of worker threads if parallel=True
        """
        if not parallel:
            # Serial processing (usually faster for this step due to overhead)
            for frame in self.frames:
                frame.detect_sources(binning=binning)
        else:
            # Parallel processing option
            def detect_sources_static(args):
                frame_idx, hdu_data, binning_factor = args
                h, w = hdu_data.shape
                binned_image = hdu_data.reshape(
                    h // binning_factor, binning_factor,
                    w // binning_factor, binning_factor
                ).mean(axis=(1, 3))
                sources = aa._find_sources(binned_image)
                return frame_idx, sources * binning_factor

            args_list = [
                (i, frame.hdu.data, binning)
                for i, frame in enumerate(self.frames)
            ]

            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                results = executor.map(detect_sources_static, args_list)
                for frame_idx, sources in results:
                    self.frames[frame_idx].sources = sources

    def align_frames(self, target_index: Optional[int] = None) -> None:
        """
        Align all frames to a target reference frame.

        Args:
            target_index: Index of frame to use as reference (default: middle frame)
        """
        if target_index is not None:
            self.target_index = target_index

        target_sources = self.frames[self.target_index].sources

        for frame in self.frames:
            frame.find_transform(target_sources)

    def apply_transforms(self, n_workers: Optional[int] = None) -> None:
        """
        Apply transformations to all frames in parallel.

        Args:
            n_workers: Number of worker threads (default: auto)
        """
        target_data = self.frames[self.target_index].hdu.data

        # Prepare arguments for parallel processing (avoid pickling frame objects)
        args_list = [
            (frame.hdu, frame.transforms, target_data, i)
            for i, frame in enumerate(self.frames)
        ]

        def process_frame_static(args):
            """Static function for parallel processing."""
            hdu, transforms, target_data, frame_idx = args

            # Convert Bayer pattern to RGB
            bayer_data = hdu.data.astype(np.uint16)
            bayer_pattern = hdu.header["BAYERPAT"]
            color_code = getattr(cv2, f"COLOR_Bayer{bayer_pattern}2RGB")
            rgb = cv2.cvtColor(bayer_data, color_code)

            # Apply alignment transform if available
            if transforms is not None:
                aligned_rgb, footprint = aa.apply_transform(transforms, rgb, target_data)
            else:
                aligned_rgb = rgb
                footprint = np.ones(rgb.shape[:2], dtype=bool)

            return frame_idx, aligned_rgb, footprint

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = executor.map(process_frame_static, args_list)
            for frame_idx, aligned_rgb, footprint in results:
                self.frames[frame_idx].aligned_rgb_image = aligned_rgb
                self.frames[frame_idx].footprint = footprint

    def _stack_single_channel(self, args):
        """
        Stack a single channel (R, G, or B) with sigma clipping.

        Helper function for parallel channel processing.
        """
        channel_data, sigma_clip, method = args
        # channel_data shape: (N_frames, H, W) - single channel

        # Apply sigma clipping if requested
        if sigma_clip is not None and channel_data.shape[0] > 1:
            mu = np.nanmean(channel_data, axis=0)
            sd = np.nanstd(channel_data, axis=0)
            lo = mu - sigma_clip * sd
            hi = mu + sigma_clip * sd
            channel_data = np.where(
                (channel_data < lo) | (channel_data > hi),
                np.nan,
                channel_data
            )

        # Combine frames
        if method == "median":
            result = np.nanmedian(channel_data, axis=0)
        else:  # mean
            result = np.nanmean(channel_data, axis=0)

        return result

    def stack(
        self,
        method: str = "mean",
        sigma_clip: Optional[float] = 3.0,
        parallel_channels: bool = True
    ) -> np.ndarray:
        """
        Stack aligned frames into a single image.

        Args:
            method: Stacking method - 'mean' or 'median'
            sigma_clip: Sigma value for outlier rejection (None to disable)
            parallel_channels: Process R, G, B channels in parallel (recommended)

        Returns:
            Stacked RGB image
        """
        if method not in ["mean", "median"]:
            raise ValueError("method must be 'mean' or 'median'")

        # Collect aligned RGB images
        aligned_images = [
            frame.aligned_rgb_image
            for frame in self.frames
            if frame.is_aligned
        ]

        if not aligned_images:
            raise RuntimeError("No successfully aligned frames to stack")

        stack_rgb = np.stack(aligned_images, axis=0)
        n_frames, height, width, channels = stack_rgb.shape

        if parallel_channels:
            # Process each channel (R, G, B) in parallel
            self.stacked_rgb = np.zeros((height, width, channels), dtype=np.float32)

            # Prepare arguments for each channel
            channel_args = [
                (stack_rgb[:, :, :, c], sigma_clip, method)
                for c in range(channels)
            ]

            # Process in parallel
            with ThreadPoolExecutor(max_workers=channels) as executor:
                channel_results = list(executor.map(self._stack_single_channel, channel_args))

            # Reassemble channels
            for c, channel_result in enumerate(channel_results):
                self.stacked_rgb[:, :, c] = channel_result
        else:
            # Original serial processing (all channels together)
            # Apply sigma clipping if requested
            if sigma_clip is not None and stack_rgb.shape[0] > 1:
                mu = np.nanmean(stack_rgb, axis=0)
                sd = np.nanstd(stack_rgb, axis=0)
                lo = mu - sigma_clip * sd
                hi = mu + sigma_clip * sd
                stack_rgb = np.where(
                    (stack_rgb < lo) | (stack_rgb > hi),
                    np.nan,
                    stack_rgb
                )

            # Combine frames
            if method == "median":
                self.stacked_rgb = np.nanmedian(stack_rgb, axis=0)
            else:  # mean
                self.stacked_rgb = np.nanmean(stack_rgb, axis=0)

        # Compute combined footprint
        footprint_list = [
            frame.footprint
            for frame in self.frames
            if frame.is_aligned
        ]
        stack_footprint = np.stack(footprint_list, axis=0)
        self.stacked_footprint = np.sum(np.invert(stack_footprint), axis=0)

        return self.stacked_rgb

    def detect_stars_in_stack(self, threshold_sigma: float = 5.0) -> Table:
        """
        Detect stars in the stacked image.

        Args:
            threshold_sigma: Detection threshold in units of background RMS

        Returns:
            Astropy Table of detected sources
        """
        if self.stacked_rgb is None:
            raise RuntimeError("Must run stack() before detecting stars")

        # Use sum of RGB channels for detection
        image = np.sum(self.stacked_rgb, axis=2)

        # Background subtraction and source extraction
        bkg = sep.Background(image)
        sources = sep.extract(
            image - bkg.back(),
            threshold_sigma * bkg.globalrms
        )
        sources.sort(order="flux")

        self._stars_table = Table(sources)
        return self._stars_table

    def create_stacked_header(self) -> fits.Header:
        """
        Create a combined FITS header for the stacked image.

        Returns:
            Combined FITS header
        """
        if not HAS_FHU:
            # Basic header if fits_header_utils not available
            header = self.frames[self.target_index].hdu.header.copy()
            header['COMMENT'] = f'Stacked from {len(self.frames)} frames'
            self.stacked_header = header
            return header

        # Use fits_header_utils if available
        data_dict = {
            str(frame.filepath): {"hdu": frame.hdu}
            for frame in self.frames
        }
        fnames = [str(frame.filepath) for frame in self.frames]
        self.stacked_header = fhu.create_stacked_header(data_dict, fnames)
        return self.stacked_header

    def save(
        self,
        filepath: Union[str, Path],
        overwrite: bool = True
    ) -> None:
        """
        Save the stacked image to a FITS file.

        Args:
            filepath: Output file path
            overwrite: Whether to overwrite existing file
        """
        if self.stacked_rgb is None:
            raise RuntimeError("Must run stack() before saving")

        filepath = Path(filepath)

        # Create header
        if self.stacked_header is None:
            self.create_stacked_header()

        # Create HDU list
        if HAS_FHU and self._stars_table is not None:
            # Use fits_header_utils to create RGB FITS with star catalog
            hdul = fhu.make_stacked_rgb_fits(
                self.stacked_header,
                self.stacked_rgb,
                self.stacked_footprint,
                self._stars_table
            )
        else:
            # Create basic RGB FITS
            primary_hdu = fits.PrimaryHDU(
                data=self.stacked_rgb,
                header=self.stacked_header
            )
            footprint_hdu = fits.ImageHDU(
                data=self.stacked_footprint,
                name='FOOTPRINT'
            )
            hdul = fits.HDUList([primary_hdu, footprint_hdu])

        hdul.writeto(filepath, overwrite=overwrite)

    def process(
        self,
        binning: int = 2,
        method: str = "mean",
        sigma_clip: Optional[float] = 3.0,
        detect_stars: bool = True,
        n_workers: Optional[int] = None,
        parallel_channels: bool = True
    ) -> np.ndarray:
        """
        Complete processing pipeline: detect, align, and stack.

        Args:
            binning: Binning factor for source detection
            method: Stacking method - 'mean' or 'median'
            sigma_clip: Sigma value for outlier rejection
            detect_stars: Whether to detect stars in final stack
            n_workers: Number of worker threads for parallel processing
            parallel_channels: Process RGB channels in parallel during stacking (recommended)

        Returns:
            Stacked RGB image
        """
        self.detect_all_sources(binning=binning)
        self.align_frames()
        self.apply_transforms(n_workers=n_workers)
        self.stack(method=method, sigma_clip=sigma_clip, parallel_channels=parallel_channels)
        
        if detect_stars:
            self.detect_stars_in_stack()
        
        return self.stacked_rgb
    
    @property
    def n_frames(self) -> int:
        """Number of frames in collection."""
        return len(self.frames)
    
    @property
    def n_aligned(self) -> int:
        """Number of successfully aligned frames."""
        return sum(frame.is_aligned for frame in self.frames)
    
    def __len__(self) -> int:
        return len(self.frames)
    
    def __getitem__(self, index: int) -> RawFrame:
        return self.frames[index]
    
    def __repr__(self) -> str:
        return (
            f"FrameCollection({self.n_frames} frames, "
            f"{self.n_aligned} aligned)"
        )


def simple_normalize(rgb: np.ndarray, percentiles: Tuple[float, float] = (1, 99)) -> np.ndarray:
    """
    Normalize RGB image for display using percentile stretching.
    
    Args:
        rgb: RGB image array (H, W, 3)
        percentiles: Lower and upper percentile values
        
    Returns:
        Normalized RGB image in [0, 1] range
    """
    result = np.zeros_like(rgb, dtype=np.float32)
    p_low, p_high = percentiles
    
    for i in range(3):
        p1, p99 = np.percentile(rgb[:, :, i], [p_low, p_high])
        result[:, :, i] = np.clip((rgb[:, :, i] - p1) / (p99 - p1), 0, 1)
    
    return result


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from time  import time

    start = time()
    collection = FrameCollection.from_directory("D:/Seestar/NGC 188_sub", pattern="*.fit")
    stacked = collection.process(method="mean", sigma_clip=3.0)
    print(time()-start)

    plt.imshow(simple_normalize(stacked))
    plt.title(f'Stacked {collection.n_aligned} images')
    plt.show()
