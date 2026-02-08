"""
Benchmark script to compare original vs refactored stacking performance.
"""

from time import time
from ..stacking import FrameCollection


def benchmark_refactored(dir_name: str, verbose: bool = True):
    """Benchmark the refactored code."""
    times = {}
    
    total_start = time()
    
    # Create collection (with parallel FITS loading)
    start = time()
    collection = FrameCollection.from_directory(dir_name)  # , lazy_load=True
    times['loading_files'] = time() - start
    
    # Detect sources
    start = time()
    collection.detect_all_sources(binning=2)
    times['finding_stars'] = time() - start
    
    # Find transforms
    start = time()
    collection.align_frames()
    times['finding_transforms'] = time() - start
    
    # Apply transforms (parallel)
    start = time()
    collection.apply_transforms()
    times['applying_transforms'] = time() - start
    
    # Stack
    start = time()
    collection.stack(method="mean", sigma_clip=3.0)
    times['stacking_images'] = time() - start
    
    # Detect stars in stack
    start = time()
    collection.detect_stars_in_stack()
    times['detecting_stars_in_stack'] = time() - start
    
    times['total'] = time() - total_start
    
    if verbose:
        print("\n=== Refactored Code Benchmark ===")
        print(f"Loading files:        {times['loading_files']:.3f}s")
        print(f"Finding stars:        {times['finding_stars']:.3f}s")
        print(f"Finding transforms:   {times['finding_transforms']:.3f}s")
        print(f"Applying transforms:  {times['applying_transforms']:.3f}s")
        print(f"Stacking images:      {times['stacking_images']:.3f}s")
        print(f"Detecting stars:      {times['detecting_stars_in_stack']:.3f}s")
        print(f"{'='*33}")
        print(f"TOTAL:                {times['total']:.3f}s")
        print(f"Frames: {collection.n_frames}, Aligned: {collection.n_aligned}")
    
    return times, collection


def benchmark_simple_api(dir_name: str, verbose: bool = True):
    """Benchmark using the simple one-line API."""
    start = time()
    
    collection = FrameCollection.from_directory(dir_name)
    stacked = collection.process()
    
    elapsed = time() - start



    if verbose:
        print(f"\n=== Simple API Benchmark ===")
        print(f"TOTAL: {elapsed:.3f}s")
        print(f"Frames: {collection.n_frames}, Aligned: {collection.n_aligned}")
    
    return elapsed, collection


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        dir_name = sys.argv[1]
    else:
        # Default test directory
        dir_name = "D:/Seestar/NGC 188_sub"
    
    print(f"Benchmarking with: {dir_name}")
    
    # Detailed benchmark
    times, collection = benchmark_refactored(dir_name)
    
    # Simple API benchmark (in a separate run)
    # elapsed, collection = benchmark_simple_api(dir_name)
