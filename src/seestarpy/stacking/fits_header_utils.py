"""
Functions for creating proper FITS headers and saving stacked RGB images
"""

import numpy as np
from astropy.io import fits
from astropy.time import Time
from collections import Counter
from datetime import datetime


def create_stacked_header(data_dict, fnames):
    """
    Create a FITS header for a stacked image by aggregating info from individual frames.
    
    Parameters:
    -----------
    data_dict : dict
        Dictionary containing frame data and metadata
    fnames : list
        List of filenames
    
    Returns:
    --------
    astropy.io.fits.Header : Header for stacked image
    """
    
    # Filter to only frames that were successfully transformed
    used_fnames = [fname for fname in fnames 
                   if data_dict[fname].get("transforms") is not None]
    
    if len(used_fnames) == 0:
        raise ValueError("No successfully aligned frames to create header from")
    
    print(f"Creating header from {len(used_fnames)}/{len(fnames)} successfully aligned frames")
    
    # Collect headers from used frames
    headers = [data_dict[fname]["hdu"].header for fname in used_fnames]
    
    # Create new header
    header = fits.Header()
    
    # Standard FITS keywords
    header['SIMPLE'] = (True, 'file does conform to FITS standard')
    header['BITPIX'] = (-32, 'number of bits per data pixel (32-bit float)')
    header['NAXIS'] = (2, 'number of data axes')
    header['EXTEND'] = (True, 'FITS dataset may contain extensions')
    
    # Get first header as template for single-valued keywords
    first_header = headers[0]
    
    # Copy single-valued keywords (same across all frames)
    single_value_keys = ['TELESCOP', 'INSTRUME', 'FILTER', 'SITELAT', 'SITELONG', 
                         'FOCUSPOS', 'FOCALLEN', 'APERTURE', 'XPIXSZ', 'YPIXSZ',
                         'BAYERPAT', 'OBJECT']
    
    for key in single_value_keys:
        if key in first_header:
            header[key] = (first_header[key], first_header.comments[key])
    
    # GAIN - find most common value
    gains = [h['GAIN'] for h in headers if 'GAIN' in h]
    if gains:
        most_common_gain = Counter(gains).most_common(1)[0][0]
        header['GAIN'] = (most_common_gain, 'Gain value (most common from stack)')
        
        # Warn if gains varied
        unique_gains = set(gains)
        if len(unique_gains) > 1:
            print(f"Warning: Multiple GAIN values found: {unique_gains}. Using {most_common_gain}")
    
    # EXPTIME - sum of all exposure times
    exptimes = [h['EXPTIME'] for h in headers if 'EXPTIME' in h]
    if exptimes:
        total_exptime = sum(exptimes)
        header['EXPTIME'] = (total_exptime, 'Total exposure time in seconds (sum of stack)')
        header['EXPOSURE'] = (total_exptime, 'Total exposure time in seconds (sum of stack)')
    
    # CCD-TEMP - average temperature
    temps = [h['CCD-TEMP'] for h in headers if 'CCD-TEMP' in h]
    if temps:
        avg_temp = np.mean(temps)
        header['CCD-TEMP'] = (round(avg_temp, 2), 'Average sensor temperature in C')
    
    # DATE-OBS - earliest observation time
    date_obs_list = [h['DATE-OBS'] for h in headers if 'DATE-OBS' in h]
    if date_obs_list:
        # Parse ISO format dates and find earliest/latest
        times = [Time(date_str, format='isot') for date_str in date_obs_list]
        earliest_time = min(times)
        latest_time = max(times)
        
        header['DATE-OBS'] = (earliest_time.iso, 'Start time of first exposure')
        header['OB-START'] = (earliest_time.iso, 'Start time of observation sequence')
        header['OB-END'] = (latest_time.iso, 'End time of observation sequence')
        
        # Calculate total observation duration
        duration = (latest_time - earliest_time).to_value('sec')
        header['OBSTOTAL'] = (round(duration, 1), 'Total observation duration in seconds')
    
    # Add stacking information
    header['NIMAGES'] = (len(used_fnames), 'Number of images stacked')
    header['STACKMET'] = ('mean', 'Stacking method used')
    header['CREATOR'] = ('Python astroalign stack', 'Software that created this file')
    header['COMMENT'] = f'Stacked from {len(used_fnames)} aligned light frames'
    header['COMMENT'] = 'Created using astroalign and astropy'
    
    # Add current processing date
    header['PROCDATE'] = (datetime.utcnow().isoformat(), 'UTC date of processing')
    
    return header


def make_stacked_rgb_fits(header, stacked_rgb, footprint=None, star_table=None):
    """
    Save stacked RGB image as multi-extension FITS file.
    
    Parameters:
    -----------
    header : astropy.io.fits.Header
        FITS header for the file
    stacked_rgb : ndarray (H, W, 3)
        Stacked RGB image
    footprint : ndarray (H, W), optional
    star_table : astropy.table.Table, optional
    """
    
    # Create HDU list
    hdu_list = fits.HDUList()
    
    # Primary HDU (empty, just contains global header)
    primary_hdu = fits.PrimaryHDU()
    primary_hdu.header.update(header)
    hdu_list.append(primary_hdu)
    
    # Add each channel as an extension
    channel_names = ['RED', 'GREEN', 'BLUE']
    
    for i, name in enumerate(channel_names):
        # Extract channel
        channel_data = stacked_rgb[:, :, i].astype(np.float32)
        
        # Create image extension
        img_hdu = fits.ImageHDU(data=channel_data, name=name)
        
        # Copy relevant header info to extension
        img_hdu.header['EXTNAME'] = name
        img_hdu.header['CHANNEL'] = (i, f'Color channel index (0=R, 1=G, 2=B)')
        img_hdu.header['BUNIT'] = ('ADU', 'Physical unit of array values')
        
        hdu_list.append(img_hdu)

    if footprint is not None:
        name = "FOOTPRINT"
        foot_hdu = fits.ImageHDU(data=footprint, name=name)
        foot_hdu.header['EXTNAME'] = name
        foot_hdu.header['BUNIT'] = ('N', 'Number of frames stacked per pixel')
        hdu_list.append(foot_hdu)

    if star_table is not None:
        star_table_hdu = fits.table_to_hdu(star_table)
        star_table_hdu.header['EXTNAME'] = "STAR-TAB"
        hdu_list.append(star_table_hdu)

    return hdu_list
