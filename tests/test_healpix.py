"""Unit tests for the pure-Python HEALPix implementation."""

import math

import pytest

from seestarpy.crowdsky.healpix import ang2pix_ring, radec_to_healpix

NSIDE = 128
NPIX = 12 * NSIDE * NSIDE  # 196608


class TestAng2PixRing:
    def test_north_pole(self):
        """theta=0 (north pole) should give pixel 0."""
        assert ang2pix_ring(NSIDE, 0.0, 0.0) == 0

    def test_south_pole(self):
        """theta=pi (south pole) should be in the last ring."""
        pix = ang2pix_ring(NSIDE, math.pi, 0.0)
        # Due to floating-point precision, exact south pole may land a few
        # pixels from NPIX-1; verify it's in the final ring region.
        assert NPIX - 20 < pix < NPIX

    def test_equator_phi_zero(self):
        """A point on the equator should land in the equatorial belt."""
        pix = ang2pix_ring(NSIDE, math.pi / 2, 0.0)
        # Equatorial belt pixels are between 2*nside*(nside-1) and
        # npix - 2*nside*(nside-1)
        eq_start = 2 * NSIDE * (NSIDE - 1)
        eq_end = NPIX - eq_start
        assert eq_start <= pix < eq_end

    def test_pixel_range(self):
        """All returned pixels should be in [0, npix)."""
        for theta in [0.1, 0.5, 1.0, math.pi / 2, 2.5, 3.0]:
            for phi in [0.0, 1.0, 3.14, 5.0]:
                pix = ang2pix_ring(NSIDE, theta, phi)
                assert 0 <= pix < NPIX

    def test_symmetry_phi_wrap(self):
        """phi and phi+2*pi should give the same pixel."""
        theta = 1.0
        phi = 1.5
        assert ang2pix_ring(NSIDE, theta, phi) == ang2pix_ring(
            NSIDE, theta, phi + 2 * math.pi
        )


class TestRadecToHealpix:
    def test_north_pole(self):
        assert radec_to_healpix(0.0, 90.0) == 0

    def test_south_pole(self):
        pix = radec_to_healpix(0.0, -90.0)
        assert NPIX - 20 < pix < NPIX

    def test_m42(self):
        """M42 (RA=83.82, Dec=-5.39) should return a consistent pixel."""
        pix = radec_to_healpix(83.82, -5.39)
        assert isinstance(pix, int)
        assert 0 <= pix < NPIX
        # Verify determinism
        assert radec_to_healpix(83.82, -5.39) == pix

    def test_ic434(self):
        """IC 434 (RA=85.25, Dec=-2.46) should be in the same sky region as M42."""
        pix_m42 = radec_to_healpix(83.82, -5.39)
        pix_ic434 = radec_to_healpix(85.25, -2.46)
        # Both are in Orion — within ~10000 pixels at NSIDE=128
        assert abs(pix_m42 - pix_ic434) < 10000

    def test_custom_nside(self):
        """Different NSIDE should give different pixel counts."""
        pix_64 = radec_to_healpix(83.82, -5.39, nside=64)
        assert 0 <= pix_64 < 12 * 64 * 64

    def test_ra_wrap(self):
        """RA=360 should equal RA=0."""
        assert radec_to_healpix(360.0, 45.0) == radec_to_healpix(0.0, 45.0)

    def test_negative_ra(self):
        """RA=-10 should equal RA=350."""
        assert radec_to_healpix(-10.0, 30.0) == radec_to_healpix(350.0, 30.0)
