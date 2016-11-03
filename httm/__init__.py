"""
`httm` contains top level transformations for converting calibrates
or raw TESS full Frame FITS images between one another.
"""

# See https://docs.python.org/2/library/collections.html#collections.namedtuple for details
import numpy

from httm.data_structures import Slice, CalibratedConverter, CalibratedConverterParameters, FITSMetaData, \
    RAWConverter, RAWConverterParameters, document_parameters, calibrated_transformation_parameters, \
    raw_transformation_parameters


def write_calibrated_fits(output_file, raw_transform):
    # type: (str, RAWConverter) -> NoneType
    """
    Write a completed :py:class:`~httm.data_structures.RAWConverter` to a calibrated FITS file

    :param output_file:
    :type output_file: str
    :param raw_transform:
    :type raw_transform: :py:class:`~httm.data_structures.RAWConverter`
    """
    from astropy.io.fits import HDUList, PrimaryHDU
    from numpy import hstack
    print raw_transform
    # noinspection PyTypeChecker
    HDUList(PrimaryHDU(header=raw_transform.fits_metadata.header,
                       data=hstack([calibrated_slice.pixels
                                    for calibrated_slice in raw_transform.slices]))) \
        .writeto(output_file)


def write_raw_fits(output_file, calibrated_transform):
    # type: (str, CalibratedConverter) -> NoneType
    """
    Write a completed :py:class:`~httm.data_structures.CalibratedConverter` to a (simulated) raw FITS file

    :param output_file:
    :type output_file: str
    :param calibrated_transform:
    :type calibrated_transform: :py:class:`~httm.data_structures.CalibratedConverter`
    :rtype: NoneType
    """
    from astropy.io.fits import HDUList, PrimaryHDU
    from numpy import hstack
    # noinspection PyTypeChecker
    HDUList(PrimaryHDU(header=calibrated_transform.fits_metadata.header,
                       data=hstack([raw_slice.pixels
                                    for raw_slice in calibrated_transform.slices]))) \
        .writeto(output_file)


def make_slice_from_calibrated_data(pixels, index):
    # type: (numpy.ndarry, int) -> Slice
    """
    Construct a slice from an array of calibrated pixel data given a specified index

    :param pixels: Image pixels from the calibrated data
    :type pixels: :py:class:`numpy.ndarray`
    :param index: The index of the slice to construct
    :type index: int
    :rtype: :py:class:`~httm.data_structures.Slice`
    """
    # TODO: Add in smear and dark pixels
    image_smear_and_dark_pixels = numpy.hstack([pixels, numpy.zeros((pixels.shape[0], 20))])
    row_count = image_smear_and_dark_pixels.shape[1]
    dark_pixel_columns = numpy.zeros((11, row_count))
    return Slice(pixels=numpy.vstack([dark_pixel_columns, image_smear_and_dark_pixels, dark_pixel_columns]),
                 index=index,
                 units='electrons')


def calibrated_transformation_from_file(
        input_file,
        number_of_slices=calibrated_transformation_parameters['number_of_slices']['default'],
        video_scales=calibrated_transformation_parameters['video_scales']['default'],
        compression=calibrated_transformation_parameters['compression']['default'],
        undershoot=calibrated_transformation_parameters['undershoot']['default'],
        baseline_adu=calibrated_transformation_parameters['baseline_adu']['default'],
        drift_adu=calibrated_transformation_parameters['drift_adu']['default'],
        smear_ratio=calibrated_transformation_parameters['smear_ratio']['default'],
        clip_level_adu=calibrated_transformation_parameters['clip_level_adu']['default'],
        start_of_line_ringing=calibrated_transformation_parameters['start_of_line_ringing']['default'],
        pattern_noise=calibrated_transformation_parameters['pattern_noise']['default']):
    from astropy.io import fits
    from numpy import hsplit
    header_data_unit_list = fits.open(input_file)
    assert len(header_data_unit_list) == 1, "Only a single image per FITS file is supported"
    assert header_data_unit_list[0].data.shape[1] % number_of_slices == 0, \
        "Image did not have the specified number of slices"
    origin_file_name = None
    if isinstance(input_file, basestring):
        origin_file_name = input_file
    if hasattr(input_file, 'name'):
        origin_file_name = input_file.name
    return CalibratedConverter(
        slices=map(lambda pixel_data, index:
                   make_slice_from_calibrated_data(pixel_data, index),
                   hsplit(header_data_unit_list[0].data, number_of_slices),
                   range(number_of_slices)),
        fits_metadata=FITSMetaData(origin_file_name=origin_file_name,
                                   header=header_data_unit_list[0].header),
        parameters=CalibratedConverterParameters(
            video_scales=video_scales,
            number_of_slices=number_of_slices,
            compression=compression,
            undershoot=undershoot,
            baseline_adu=baseline_adu,
            drift_adu=drift_adu,
            smear_ratio=smear_ratio,
            clip_level_adu=clip_level_adu,
            start_of_line_ringing=start_of_line_ringing,
            pattern_noise=pattern_noise,
        ))


calibrated_transformation_from_file.__doc__ = """
Construct a :py:class:`~httm.data_structures.CalibratedConverter` from a file or file name

:param input_file: The file or file name to input
:type input_file: :py:class:`file` or :py:class:`str`
{parameter_documentation}
:rtype: :py:class:`~httm.data_structures.CalibratedConverter`
""".format(parameter_documentation=document_parameters(calibrated_transformation_parameters))


def make_slice_from_raw_data(
        image_and_smear_pixels,
        index,
        left_dark_pixel_columns,
        right_dark_pixel_columns):
    # type: (numpy.ndarray, int, numpy.ndarray, numpy.ndarray) -> Slice
    print "image_and_smear dimentions", image_and_smear_pixels.shape
    print "Index", index
    print "left dark pixels dimensions", left_dark_pixel_columns.shape
    print "right dark pixels columns", right_dark_pixel_columns.shape
    return Slice(
        pixels=numpy.vstack([left_dark_pixel_columns, image_and_smear_pixels, right_dark_pixel_columns]),
        index=index,
        units='hdu')


def raw_transformation_from_file(
        input_file,
        number_of_slices=calibrated_transformation_parameters['number_of_slices']['default'],
        video_scales=calibrated_transformation_parameters['video_scales']['default'],
        full_well=calibrated_transformation_parameters['full_well']['default'],
        compression=calibrated_transformation_parameters['compression']['default'],
        undershoot=calibrated_transformation_parameters['undershoot']['default'],
        smear_ratio=calibrated_transformation_parameters['smear_ratio']['default'],
        clip_level_adu=calibrated_transformation_parameters['clip_level_adu']['default'],
        pattern_noise=calibrated_transformation_parameters['pattern_noise']['default']):
    from astropy.io import fits
    from numpy import hsplit, vsplit
    header_data_unit_list = fits.open(input_file)
    assert len(header_data_unit_list) == 1, "Only a single image per FITS file is supported"
    assert header_data_unit_list[0].data.shape[1] % number_of_slices == 0, \
        "Image did not have the specified number of slices"
    origin_file_name = None
    if isinstance(input_file, basestring):
        origin_file_name = input_file
    if hasattr(input_file, 'name'):
        origin_file_name = input_file.name

    sliced_image_smear_and_dark_pixels = vsplit(header_data_unit_list[0].data[:, 44:-44], number_of_slices)
    sliced_left_dark_pixels = hsplit(header_data_unit_list[0].data[:, :44], number_of_slices)
    sliced_right_dark_pixels = hsplit(header_data_unit_list[0].data[:, -44:], number_of_slices)

    return RAWConverter(
        slices=map(make_slice_from_raw_data,
                   sliced_image_smear_and_dark_pixels,
                   range(number_of_slices),
                   sliced_left_dark_pixels,
                   sliced_right_dark_pixels),
        fits_metadata=FITSMetaData(origin_file_name=origin_file_name,
                                   header=header_data_unit_list[0].header),
        parameters=RAWConverterParameters(
            video_scales=video_scales,
            number_of_slices=number_of_slices,
            full_well=full_well,
            compression=compression,
            undershoot=undershoot,
            smear_ratio=smear_ratio,
            clip_level_adu=clip_level_adu,
            pattern_noise=pattern_noise,
        ))


raw_transformation_from_file.__doc__ = """
Construct a :py:class:`~httm.data_structures.RAWConverter` from a file or file name

:param input_file: The file or file name to input
:type input_file: :py:class:`File` or :py:class:`str`
{parameter_documentation}
:rtype: :py:class:`~httm.data_structures.RAWConverter`
""".format(parameter_documentation=document_parameters(raw_transformation_parameters))
