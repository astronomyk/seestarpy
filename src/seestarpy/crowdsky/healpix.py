"""Pure-Python HEALPix RING-scheme pixelisation (no external dependencies).

Implements the three-zone formula from Gorski et al. 2005 for converting
spherical coordinates to HEALPix pixel indices in the RING numbering scheme.

Only NSIDE values that are powers of 2 are supported (the standard case).
"""

import math


def ang2pix_ring(nside, theta, phi):
    """Convert spherical coordinates to a HEALPix RING pixel index.

    Parameters
    ----------
    nside : int
        HEALPix resolution parameter (must be a power of 2).
    theta : float
        Co-latitude in radians (0 at north pole, pi at south pole).
    phi : float
        Longitude in radians [0, 2*pi).

    Returns
    -------
    int
        Pixel index in the RING scheme.
    """
    nside2 = nside * nside
    npix = 12 * nside2
    phi = phi % (2.0 * math.pi)

    z = math.cos(theta)
    za = abs(z)
    tt = phi / (math.pi / 2.0)  # in [0, 4)

    if za <= 2.0 / 3.0:
        # Equatorial belt
        temp1 = nside * (0.5 + tt)
        temp2 = nside * z * 0.75

        jp = int(temp1 - temp2)  # ascending edge index
        jm = int(temp1 + temp2)  # descending edge index

        ir = nside + 1 + jp - jm  # ring number (1..4*nside-1)
        kshift = 1 - (ir & 1)  # 0 if ir odd, 1 if ir even

        ip = (jp + jm - nside + kshift + 1) // 2  # pixel number in ring
        ip = ip % (4 * nside)

        return nside * (nside - 1) * 2 + (ir - 1) * 4 * nside + ip

    else:
        # Polar caps
        tp = tt - int(tt)
        if za < 1.0 - nside2 / (3.0 * npix):
            tmp = nside * math.sqrt(3.0 * (1.0 - za))
        else:
            tmp = nside * math.sqrt(3.0) * math.sqrt(1.0 - za)

        jp = int(tp * tmp)
        jm = int((1.0 - tp) * tmp)

        ir = jp + jm + 1  # ring number
        ip = int(tt * ir)
        ip = ip % (4 * ir)

        if z > 0:
            # North polar cap
            return 2 * ir * (ir - 1) + ip
        else:
            # South polar cap
            return npix - 2 * ir * (ir + 1) + ip


def radec_to_healpix(ra_deg, dec_deg, nside=128):
    """Convert RA/Dec (degrees) to a HEALPix RING pixel index.

    Parameters
    ----------
    ra_deg : float
        Right ascension in degrees [0, 360).
    dec_deg : float
        Declination in degrees [-90, 90].
    nside : int
        HEALPix resolution parameter.  Default 128.

    Returns
    -------
    int
        Pixel index in the RING scheme.
    """
    theta = math.radians(90.0 - dec_deg)  # co-latitude
    phi = math.radians(ra_deg % 360.0)
    return ang2pix_ring(nside, theta, phi)
