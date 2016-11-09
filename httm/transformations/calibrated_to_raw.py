"""
``httm.transformations.calibrated_to_raw``
==========================================

Transformation functions for processing a
:py:class:`~httm.data_structures.calibrated_converter.CalibratedConverter` so that it is suitable for writing to a raw FITS file.

"""

import numpy

from constants import FPE_MAX_ADU
from ..data_structures.common import Slice


def add_start_of_line_ringing_to_slice(start_of_line_ringing, image_slice):
    # type: (numpy.ndarray, Slice) -> Slice
    """
    Add a fixed pattern to each row of a slice.

    :param start_of_line_ringing: One dimensional array of floats, representing noise in a row in a slice.
    :type start_of_line_ringing: row: :py:class:`numpy.ndarray`
    :param image_slice:
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype:  :py:class:`~httm.data_structures.common.Slice`
    """
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=image_slice.pixels + start_of_line_ringing)


def add_pattern_noise_to_slice(pattern_noise, image_slice):
    # type: (numpy.ndarray, Slice) -> Slice
    """
    Add a fixed pattern to a slice.

    :param pattern_noise: Two dimensional array of floats, representing noise in a slice.
    :type pattern_noise: :py:class:`numpy.ndarray`
    :param image_slice:
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype:  :py:class:`~httm.data_structures.common.Slice`
    """
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=image_slice.pixels + pattern_noise)


def introduce_smear_rows_to_slice(smear_ratio, image_slice):
    # type: (float, Slice) -> Slice
    """
    TODO: Mention that this adds non-zreo smear rows


    Estimate smear by averaging rows in the image pixels and then multiplying by ``smear_ratio``.
    For most of the frame cycle, the pixel effectively sits in the imaging area of the CCD, collecting
    photons from a particular point on the sky for the exposure time. During readout, the pixel moves
    quickly through the imaging area, exposed to each point on the sky along a column for a short time,
    the parallel clock period. The ``smear_ratio`` is the ratio of exposure time to parallel clock period.

    This function first adds up all of the rows in the image pixel subarray of the slice. It multiplies
    by smear_ratio to estimate a smear row. It then replaces the smear rows in the slice with the estimated
    smear row, and adds the estimated smear row to each image row.

    :param image_slice:
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :param smear_ratio:
    :type smear_ratio: float
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    # TODO crash if smear rows already introduced

    # TODO relative coordinates

    working_pixels = image_slice.pixels
    image_pixels = working_pixels[0:2058, 11:523]
    estimated_smear = smear_ratio * numpy.sum(image_pixels, 0)
    working_pixels[2058:2068, 11:523] = estimated_smear
    working_pixels[0:2058, 11:523] += estimated_smear
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=working_pixels)


def add_shot_noise(image_slice):
    # type: (Slice) -> Slice
    """
    Add `*shot noise* <https://en.wikipedia.org/wiki/Shot_noise>`_ to every pixel.
    *Shot noise* is a fluctuation in electron counts.

    It is modeled as a Gaussian distributed error.

    If the expected electron count in the pixel is :math:`n`
    the standard deviation of the shot noise is :math:`\\sqrt{n}` and the expected value is :math:`n`.

    :param image_slice: An image slice which has electrons as its units.  Pixel data should be the *expected* electron \
    counts for each pixel.
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    # TODO throw if units are not electrons
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=numpy.random.normal(loc=image_slice.pixels, scale=numpy.sqrt(image_slice.pixels)))


def simulate_blooming_on_slice(full_well, blooming_threshold, nreads, image_slice):
    """
    TODO. Currently done by SPyFFI

    :param image_slice:
    :param full_well:
    :param blooming_threshold:
    :param nreads:
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    # TODO crash if smear rows already introduced

    # TODO check units=electrons

    # TODO relative coordinates

    kernel = numpy.array([0.3, 0.4, 0.3])

    def diffusion_step(column):
        clipped = numpy.clip(column, 0, nreads * blooming_threshold)
        excess = column - clipped
        diffused_excess = numpy.convolve(excess, kernel, mode='same')
        return clipped + diffused_excess

    def bloom_column(column):
        column = diffusion_step(column)
        while numpy.amax(column) > nreads * full_well:
            column = diffusion_step(column)
        return column

    working_pixels = image_slice.pixels
    image_pixels = working_pixels[0:2058, 11:523]
    bloomed_pixels = numpy.apply_along_axis(bloom_column, 0, image_pixels)
    working_pixels[0:2058, 11:523] = bloomed_pixels
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=working_pixels)


def add_readout_noise_to_slice(readout_noise, nreads, image_slice):
    """
    Adds a Gaussian random _readout_ noise to every pixel.
    This noise comes from the charge sense transistor and the signal processing electronics.
    The average value :math:`\\mu` of the noise is `0`.
    The variance :math:`\\sigma^2` is :math:`\\mathtt{readout\_noise}^2 \times \\mathtt{nreads}`

    :param image_slice:
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :param readout_noise:
    :type readout_noise: float
    :param nreads:
    :type nreads: int
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    from numpy.random import normal
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=image_slice.pixels + normal(loc=0.0, scale=readout_noise * numpy.sqrt(nreads),
                                           size=image_slice.pixels.size))


# noinspection PyProtectedMember
def simulate_undershoot(undershoot, image_slice):
    """
    When you have a bright pixel, the pixel to the right of it will appear dimmer.  This is _undershoot_.

    This function simulates undershoot for a slice.

    It convolves the kernel :math:`\\langle 1, -\\mathtt{undershoot}  \\rangle` with each input row,
    yielding an output row of the same length. The convolution is non-cyclic: the input row is implicitly
    padded with zero at the start to make this true.

    :param undershoot: Undershoot parameter from parameter structure, typically `~0.001`, dimensionless
    :type undershoot: float
    :param image_slice:
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    kernel = numpy.array([1.0, -undershoot])

    def convolve_row(row):
        return numpy.convolve(row, kernel, mode='same')

    return image_slice._replace(pixels=numpy.apply_along_axis(convolve_row, 1, image_slice.pixels))


def convert_slice_electrons_to_adu(compression, number_of_exposures, video_scale, baseline_adu, image_slice):
    # type: (float, int, float, float, Slice) -> Slice
    """
    TODO

    :param compression: TODO
    :type compression: float
    :param number_of_exposures: The number of exposures the image comprises.\
    This is read from the `NREADS` header of the input FITS file. TODO: Link to header description
    :type number_of_exposures: int
    :param video_scale: TODO
    :type video_scale: float
    :param baseline_adu: TODO
    :type baseline_adu: float
    :param image_slice: TODO
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    compression_per_adu = compression / (number_of_exposures * FPE_MAX_ADU)  # type: float
    compression_per_electron = compression_per_adu / video_scale  # type: float
    exposure_baseline = baseline_adu * number_of_exposures

    def transform_electron_to_adu(electron):
        return exposure_baseline + electron / (video_scale * (1.0 + compression_per_electron * electron))

    return Slice(index=image_slice.index,
                 units="ADU",
                 pixels=transform_electron_to_adu(image_slice.pixels))


def convert_electrons_to_adu(calibrated_converter):
    # type: (CalibratedConverter) -> CalibratedConverter
    """
    Converts a :py:class:`~httm.data_structures.calibrated_converter.CalibratedConverter` from having electrons
    to *Analogue to Digital Converter Units* (ADU).

    :param calibrated_converter: Should have electrons for units for each of its slices
    :type calibrated_converter: :py:class:`~httm.data_structures.calibrated_converter.CalibratedConverter`
    :rtype: :py:class:`~httm.data_structures.calibrated_converter.CalibratedConverter`
    """
    video_scales = calibrated_converter.parameters.video_scales
    image_slices = calibrated_converter.slices
    # TODO: NREADS should be read from parameters
    number_of_exposures = calibrated_converter.fits_metadata.header['NREADS']
    compression = calibrated_converter.parameters.compression
    baseline_adu = calibrated_converter.parameters.baseline_adu
    assert len(video_scales) == len(image_slices), "Video scales do not match image slices"
    # noinspection PyProtectedMember
    return calibrated_converter._replace(
        slices=tuple(
            convert_slice_electrons_to_adu(compression, number_of_exposures, video_scale, image_slice, baseline_adu)
            for (video_scale, image_slice) in zip(video_scales, image_slices)))
