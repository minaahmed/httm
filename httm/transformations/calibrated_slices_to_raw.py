"""
``httm.transformations.calibrated_slices_to_raw``
=================================================

Transformation functions for processing slices contained in a
:py:class:`~httm.data_structures.calibrated_converter.SingleCCDCalibratedConverter` so that they are suitable
for writing to a simulated raw FITS file.

"""

import numpy

from constants import FPE_MAX_ADU
from ..data_structures.common import Slice


# noinspection PyProtectedMember


def add_start_of_line_ringing_to_slice(start_of_line_ringing, image_slice):
    # type: (numpy.ndarray, Slice) -> Slice
    """
    Every uncalibrated row of pixels (dark or otherwise) in a CCD slice
    has been observed in the lab to start with a fixed pattern.

    This pattern is referred to as the *start of line ringing*.

    This transformation introduces the *start of line ringing* pattern to each row.

    *Start of line ringing* differs from CCD to CCD and slice to slice.

    It is most prominent in the left dark pixel columns.

    :param start_of_line_ringing: One dimensional array of floats, representing a fixed pattern \
    disturbance in each row of a slice.
    :type start_of_line_ringing: row: :py:class:`numpy.ndarray`
    :param image_slice: input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice` units: electrons
    :rtype:  :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=image_slice.pixels + start_of_line_ringing)


def add_pattern_noise_to_slice(pattern_noise, image_slice):
    # type: (numpy.ndarray, Slice) -> Slice
    """
    This transformation adds a fixed pattern of noise to a slice.

    The fixed pattern noise is different for each slice, for each CCD.

    The default values should be zero, because the expected pattern noise is zero.

    This transformation is present to accommodate the flight electronics where *pattern noise* may be present.

    :param pattern_noise: A two dimensional array of floats, representing a fixed pattern \
    disturbance in a slice.
    :type pattern_noise: :py:class:`numpy.ndarray`
    :param image_slice: The input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype:  :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=image_slice.pixels + pattern_noise)


def introduce_smear_rows_to_slice(smear_ratio, image_slice):
    # type: (float, Slice) -> Slice
    """
    This function takes a slice with empty smear rows and populates them, and adds smear to every image pixel
    (but not dark pixels). See :ref:`ccd-and-slice-layout` for more details.

    *Smear* is estimated by averaging rows in the image pixels and then multiplying by ``smear_ratio``.
    For most of the frame cycle, a pixel effectively sits in the imaging area of the CCD, collecting
    photons from a particular point on the sky for the exposure time. During readout, that pixel moves
    quickly through the imaging area, exposed to each point on the sky along a column for a short time,
    the parallel clock period. The ``smear_ratio`` is the ratio of parallel clock period to the
    nominal exposure time of a single frame.

    This function first adds up all of the rows in the image pixel subarray of the slice. It multiplies
    that sum by ``smear_ratio`` to estimate a smear row. It then replaces the corresponding empty smear rows in the
    slice with the estimated smear row. Finally, it adds the estimated smear row to each image row.

    The pixels in the resulting smear rows should all be nonzero for reasonable input data,
    but if this transformation has not been applied, they should always contain zeros for a slice of calibrated data.

    :param image_slice: input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :param smear_ratio: dimensionless ratio of smear exposure to nominal exposure
    :type smear_ratio: float
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    assert False, "Smear rows are already introduced (should be set to 0)"

    # TODO relative coordinates

    working_pixels = image_slice.pixels
    image_pixels = working_pixels[0:2058, 11:523]
    estimated_smear = smear_ratio * numpy.sum(image_pixels, 0)
    working_pixels[2058:2068, 11:523] = estimated_smear
    working_pixels[0:2058, 11:523] += estimated_smear
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=working_pixels)


def add_shot_noise_to_slice(image_slice):
    # type: (Slice) -> Slice
    """
    This transformation adds `shot noise <https://en.wikipedia.org/wiki/Shot_noise>`_ to every pixel.

    *Shot noise* is a fluctuation in electron counts.

    It is modeled as a Gaussian distributed error.

    If the expected electron count in the pixel is :math:`n`
    the standard deviation :math:`\\sigma` of the shot noise is :math:`\\sqrt{n}` and the expected value
    :math:`\\mu` is :math:`n`.

    :param image_slice: An image slice which has electrons as its units.  Pixel data should be the *expected* electron \
    counts for each pixel.
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=numpy.random.normal(loc=image_slice.pixels, scale=numpy.sqrt(image_slice.pixels)))


def simulate_blooming_on_slice(full_well, blooming_threshold, number_of_exposures, image_slice):
    # type: (float, float, int, Slice) -> Slice
    """
    This function simulates `blooming <http://hamamatsu.magnet.fsu.edu/articles/ccdsatandblooming.html>`_ along columns
    in the image pixel array.

    Blooming is a diffusion process involving thermal excitation of electrons over the potential barriers
    between pixels. The height of the potential barrier confining electrons to the pixel decreases as
    the electron count in the pixel increases. The diffusion rate grows exponentially with decreasing barrier
    height.

    This process is modeled using three parameters:

      - ``full_well``, the maximum number of electrons in a pixel. This is the number of electrons sufficient to cause
         such rapid diffusion that the pixel cannot hold any more.
      - ``blooming_threshold``, the number of electrons in the pixel that suffices to drive significant diffusion.
      - ``number_of_exposures``, the number of stacked images in the slice.

    Blooming is modeled as a diffusion process.

    In a single step of the diffusion process, those pixels with electrons above
    :math:`\\mathtt{number\_of\_exposures} \\times \\mathtt{blooming\_threshold}` electrons diffuse charge to
    neighboring pixels in the same column.

    A single step of the diffusion process is always performed *at least once*.

    The single step is repeated until all pixels are below
    :math:`\\mathtt{number\_of\_exposures} \\times \\mathtt{full\_well}`.

    :param full_well: The maximum number of electrons in a pixel.
    :type full_well: float
    :param blooming_threshold: The number of electrons in the pixel that suffices to drive significant diffusion.
    :type blooming_threshold: float
    :param number_of_exposures: The number of stacked images in the slice
    :type number_of_exposures: int
    :param image_slice: Input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    convolutional_kernel = numpy.array([0.3, 0.4, 0.3])

    def diffusion_step(column):
        diffusion_proof_part = numpy.clip(column, 0, number_of_exposures * blooming_threshold)
        excess = column - diffusion_proof_part
        # implicitly lose charge from top and bottom
        diffused_excess = numpy.convolve(excess, convolutional_kernel, mode='same')
        return diffusion_proof_part + diffused_excess

    def bloom_column(column):
        column = diffusion_step(column)
        while numpy.amax(column) > number_of_exposures * full_well:
            column = diffusion_step(column)
        return column

    working_pixels = image_slice.pixels
    image_pixels = working_pixels[0:2058, 11:523]
    bloomed_pixels = numpy.apply_along_axis(bloom_column, 0, image_pixels)
    working_pixels[0:2058, 11:523] = bloomed_pixels
    # noinspection PyProtectedMember
    return image_slice._replace(pixels=working_pixels)


def add_readout_noise_to_slice(readout_noise_parameter, number_of_exposures, image_slice):
    """
    This transformation a Gaussian random *readout* noise to every pixel.

    This noise comes from the charge sense transistor and the signal processing electronics.

    The average value :math:`\\mu` of the noise is `0`.

    The variance :math:`\\sigma^2` is :math:`\\mathtt{readout\_noise\_parameter}^2 \\times \\mathtt{number\_of\_exposures}`.

    :param readout_noise_parameter: noise standard deviation for one image
    :type readout_noise_parameter: float
    :param number_of_exposures: number of stacked images in the slice
    :type number_of_exposures: int
    :param image_slice: input slice
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    # noinspection PyProtectedMember
    return image_slice._replace(
        pixels=numpy.random.normal(loc=image_slice.pixels,
                                   scale=readout_noise_parameter * numpy.sqrt(number_of_exposures)))


def simulate_undershoot_on_slice(undershoot_parameter, image_slice):
    """
    When a CCD reads out a bright pixel, the pixel to the right of it appears artificially dimmer.

    This is *undershoot*.

    This function simulates *undershoot* for a slice.

    It convolves the kernel :math:`\\langle 1, -\\mathtt{undershoot\_parameter}  \\rangle` with each input row,
    yielding an output row of the same length.

    The convolution is non-cyclic: the input row is implicitly padded with zero at the start to make this true.

    :param undershoot_parameter: Typically `~0.001`, dimensionless
    :type undershoot_parameter: float
    :param image_slice: input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """
    assert image_slice.units == "electrons", "units must be electrons"
    convolutional_kernel = numpy.array([1.0, -undershoot_parameter])

    def convolve_row(row):
        return numpy.convolve(row, convolutional_kernel, mode='same')

    # noinspection PyProtectedMember
    return image_slice._replace(pixels=numpy.apply_along_axis(convolve_row, 1, image_slice.pixels))


def convert_slice_electrons_to_adu(gain_loss, number_of_exposures, video_scale, baseline_adu, clip_level_adu,
                                   image_slice):
    # type: (float, int, float, float, int, Slice) -> Slice
    """
    This functions simulate various nonlinear effects in the measurement of electrons, before finally yielding output
    in *Analogue To Digital Converter Units* (ADU).

    The other transformation functions handle linear and approximately linear effects. This
    transformation is more complex and has more parameters because nonlinear effects are not
    so easily disentangled.

    Define the following values:

    :math:`\\displaystyle{\\mathtt{FPE\\_MAX\\_ADU} := 65535}`

    :math:`\\displaystyle{\\mathtt{gain\\_loss\\_per\\_adu} := \\frac{\\mathtt{gain\\_loss}}
    {\\mathtt{number\\_of\\_exposures}\\times\\mathtt{FPE\\_MAX\\_ADU}}}`

    :math:`\\displaystyle{\\mathtt{gain\\_loss\\_per\\_electron} := \\frac{\\mathtt{gain\\_loss\\_per\\_adu}}
    {\\mathtt{video\\_scale}}}`

    :math:`\\displaystyle{\\mathtt{exposure\\_baseline} := \\mathtt{baseline\\_adu}
    \\times\\mathtt{number\\_of\\_exposures}}`

    :math:`\\displaystyle{\\mathtt{exposure\\_clip\\_level} := \\mathtt{clip\\_level\\_adu}
    \\times\\mathtt{number\\_of\\_exposures}}`

    :math:`\\displaystyle{\\mathtt{clip}(x,a,b) := \\max(a,\\min(x,b))}`

    For each pixel :math:`p`, with units in electrons, this function applies the following
    transformation:

    :math:`\\mathtt{clip}(\\displaystyle{\\mathtt{exposure\\_baseline}
    + \\frac{p}{\\mathtt{video\\_scale} \\times (1 + \\mathtt{gain\\_loss\\_per\\_electron} \\times p)}}, 0,
    \\mathtt{exposure\\_clip\\_level})`

    This transformation affects all pixels, dark, smear or illuminated.

    :param gain_loss: The relative decrease in video gain over the total ADC range
    :type gain_loss: float
    :param number_of_exposures: The number of exposures the image comprises.
    :type number_of_exposures: int
    :param video_scale: Constant for converting electron counts to \
    *Analogue to Digital Converter Units* (ADU). Units: electrons per ADU
    :type video_scale: float
    :param baseline_adu: Analog to digital converter output for zero electrons. Units: ADU
    :type baseline_adu: float
    :param clip_level_adu: Maximum analog to digital converter output. Units: ADU
    :type clip_level_adu: int
    :param image_slice: Input slice. Units: electrons
    :type image_slice: :py:class:`~httm.data_structures.common.Slice`
    :rtype: :py:class:`~httm.data_structures.common.Slice`
    """

    assert image_slice.units == "electrons", "units must be electrons"
    gain_loss_per_adu = gain_loss / (number_of_exposures * FPE_MAX_ADU)  # type: float
    gain_loss_per_electron = gain_loss_per_adu / video_scale
    exposure_baseline = baseline_adu * number_of_exposures
    exposure_clip_level = clip_level_adu * number_of_exposures

    def transform_electron_to_adu(electron):
        from numpy import clip
        return clip(
            exposure_baseline + electron / (video_scale * (1.0 + gain_loss_per_electron * electron)),
            0, exposure_clip_level)

    return Slice(index=image_slice.index,
                 units="ADU",
                 pixels=transform_electron_to_adu(image_slice.pixels))
