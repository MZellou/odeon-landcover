import os
from math import isclose
import numpy as np
import rasterio
from rasterio import features
from rasterio.windows import Window
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from odeon import LOGGER

IMAGE_TYPE = {"uint8": [0, 0, 2**8 - 1, np.uint8, rasterio.uint8],
              "uint16": [1, 0, 2**16 - 1, np.uint16, rasterio.uint16],
              "uint32": [2, 0, 2**32 - 1, np.uint32, rasterio.uint32]
              }


def rasterize_shape(tuples, meta, shape, fill=0, default_value=1):
    """

    Parameters
    ----------
    tuples :list[tuples]
    meta : dict
    shape
    fill : int
    default_value

    Returns
    -------

    """
    raster = features.rasterize(tuples,
                                out_shape=shape,
                                default_value=default_value,
                                transform=meta["transform"],
                                dtype=rasterio.uint8,
                                fill=fill)
    return raster


def get_window_param(center, dataset, width, height):
    """
    get window left right top bottom to exctract path from the Raster

    Parameters
    ----------
    center : pandas.core.series.Series
     a row from a pandas DataFrame
    dataset : rasterio.DatasetReader
     a Rasterio Dataset to get the row, col from x, y in GeoCoordinate
     this is where we will extract path
    width : float
     width in Geocoordinate
    height : float
     height GeoCoordinate

    Returns
    -------
    Tuple
     col, row, width, height

    """

    row, col = dataset.index(center.x, center.y)
    col_s = int(height / 2)
    row_s = int(width / 2)
    return col - col_s, row - row_s, width, height


def get_bounds(x, y, width, height, resolution_x, resolution_y):
    """
    get window left right top bottom to exctract path from the Raster

    Parameters
    ----------
    center : pandas.core.series.Series
     a row from a pandas DataFrame
    dataset : rasterio.DatasetReader
     a Rasterio Dataset to get the row, col from x, y in GeoCoordinate
     this is where we will extract path
    width : float
     width in Geocoordinate
    height : float
     height GeoCoordinate

    Returns
    -------
    Tuple
     col, row, width, height

    """

    x_side = 0.5 * width * resolution_x
    y_side = 0.5 * height * resolution_y
    left, top, right, bottom = x - x_side, y + y_side, x + x_side, y - y_side
    return left, bottom, right, top


def get_scale_factor_and_img_size(target_raster, resolution, width, height):
    """

    Parameters
    ----------
    target_raster : str
     the raster path where we want to get the scaled factors to fit the
     targeted resolution
    resolution : tuple[float, float]
     the targeted resolution
    width : int
     the original width of patch
    height : int
     the original height of patch

    Returns
    -------

    """
    with rasterio.open(target_raster) as target:

        x_close = isclose(target.res[0], resolution[0], rel_tol=1e-04)
        y_close = isclose(target.res[1], resolution[1], rel_tol=1e-04)

        if x_close and y_close:

            return 1, 1, width, height
        else:

            x_scale = target.res[0] / resolution[0]
            y_scale = target.res[1] / resolution[1]
            scaled_width = width / x_scale
            scaled_height = height / y_scale

            return x_scale, y_scale, scaled_width, scaled_height


def create_patch_from_center(out_file, msk_raster, meta, window, resampling):
    """Create tile from center

    Parameters
    ----------
    out_file: str
    msk_raster : tif of raster
    meta : dict
     geo metadata in gdal format
    window : rasterio.window.Window
     rasterio window
    resampling : rasterio.enums.Resampling
     resampling method (billinear, cubic, etc.)

    Returns
    -------

    """

    with rasterio.open(msk_raster) as dst:

        clip = dst.read(window=window, out_shape=(meta["count"], meta["height"], meta["width"]), resampling=resampling)

        with rasterio.open(out_file, 'w', **meta) as raster_out:

            raster_out.write(clip)

        return window


def check_proj(dict_of_raster):
    """

    Parameters
    ----------
    dict_of_raster : dict
     dictionary of raster name, raster file path and band list

    Returns
    -------
    boolean
     True if all rasters have same crs
    """
    check = True
    crs_compare = None

    for raster_name, raster in dict_of_raster.items():

        with rasterio.open(raster) as src:

            crs = src.meta["crs"]
            crs_compare = crs if crs_compare is None else crs_compare

            if crs_compare != crs:
                check = False

    return check


def stack_window_raster(center,
                        dict_of_raster,
                        meta,
                        mns_mnt,
                        compute_only_masks=False,
                        raster_out=None,
                        meta_msk=None):
    """stack band at window level of geotif layer and create a
    couple patch image and patch mask

    Parameters
    ----------
    center : pandas.core.series.Series
     a row from a pandas DataFrame
    dict_of_raster : dict[str, str]
     dictionary of layer geo tif (RGB, CIR, etc.)
    meta : dict
     metadata for the window raster
    mns_mnt : boolean
     rather calculate or not DMS - DMT and create a new band with it
    compute_only_masks : int (0,1)
     rather compute only masks or not
    raster_out: str
     path of rasterized full mask where to extract the window mask
    meta_msk: dict
     metadata in rasterio format for raster mask

    Returns
    -------
        None
    """
    if os.path.isfile(center["img_file"]):

        os.remove(center["img_file"])

    rasters: dict = dict_of_raster.copy()
    resampling = Resampling.bilinear

    def _get_window(dataset, raster):
        """

        Parameters
        ----------
        dataset : rasterio.DataSetReader
         dataset where to exctract window
        raster : dict
         raster params

        Returns
        -------
        window : rasterio.Windows
        """

        scaled_width = raster["scaled_width"]
        scaled_height = raster["scaled_height"]

        left, bottom, right, top = get_bounds(center.x,
                                              center.y,
                                              scaled_width,
                                              scaled_height,
                                              dataset.res[0],
                                              dataset.res[1])

        returned_window = from_bounds(left, bottom, right, top, dataset.transform)
        """
        col_off, row_off, _, _ = get_window_param(center,
                                                  dataset,
                                                  scaled_width,
                                                  scaled_height)
        returned_window = Window(col_off, row_off, scaled_width, scaled_height)
        """
        return returned_window

    raster: dict = next(iter(dict_of_raster.values()))

    with rasterio.open(raster["path"]) as src:

        window = _get_window(src, raster)
        meta_msk["transform"] = rasterio.windows.transform(window, src.transform)
        meta["transform"] = rasterio.windows.transform(window, src.transform)

    with rasterio.open(center["img_file"], 'w', **meta) as dst:

        idx = 1

        """ handle the special case MNS-MNT"""
        dtype = meta["dtype"]
        first = True

        for raster_name, raster in rasters.items():

            if raster_name in ["DSM", "DTM"] and mns_mnt:

                break

            else:

                with rasterio.open(raster["path"]) as src:

                    if first:

                        first = False

                        create_patch_from_center(center["msk_file"],
                                                 raster_out,
                                                 meta_msk,
                                                 window,
                                                 resampling)

                    if compute_only_masks == 0:

                        if first is False:

                            window = _get_window(src, raster)

                        for i in raster["bands"]:

                            band = src.read(i,
                                            window=window,
                                            out_shape=(1,
                                                       meta["height"],
                                                       meta["width"]),
                                            resampling=resampling
                                            )
                            if src.meta["dtype"] != meta["dtype"]:

                                band = normalize_array_in(band,
                                                          meta["dtype"],
                                                          IMAGE_TYPE[meta["dtype"]][2])

                            dst.write_band(idx, band)
                            idx += 1

        if ("DSM" and "DTM") in rasters and mns_mnt:

            with rasterio.open(rasters["DSM"]["path"]) as dsm_ds:

                dsm_window = _get_window(dsm_ds, rasters["DSM"])

                with rasterio.open(rasters["DTM"]["path"]) as dtm_ds:

                    dtm_window = _get_window(dtm_ds, rasters["DTM"])

                    if first:

                        create_patch_from_center(center["msk_file"],
                                                 raster_out,
                                                 meta_msk,
                                                 dsm_window,
                                                 resampling)
                    if compute_only_masks is False:

                        band = add_height(dsm_ds,
                                          dtm_ds,
                                          meta,
                                          dtype=dtype,
                                          dsm_window=dsm_window,
                                          dtm_window=dtm_window,
                                          height=meta["height"],
                                          width=meta["width"],
                                          resampling=resampling)

                        dst.write_band(idx, band)
                        idx += 1


def count_band_for_stacking(dict_of_raster):
    """
    take a dictionnary of raster (name of raster, path_to_file)
    and return the number of band necessary to stack them in a single raster
    Parameters
    ----------
    dict_of_raster: dict

    Returns
    -------
    int
    """

    nb_of_necessary_band = 0
    rasters: dict = dict_of_raster.copy()

    if ("DSM" and "DTM") in rasters:

        nb_of_necessary_band += 1

    rasters.pop("DSM", None)
    rasters.pop("DTM", None)

    for raster_name, raster in rasters.items():

        with rasterio.open(raster) as src:

            count = src.meta["count"]
            nb_of_necessary_band += count

    return nb_of_necessary_band


def add_height(dsm_ds,
               dtm_ds,
               meta,
               dtype=np.uint8,
               dsm_window=None,
               dtm_window=None,
               height=None,
               width=None,
               resampling=None):
    """
    Build the height band from mns and mnt :
    first it applies a difference and then a linear scale

    As a remainder, the previous computation used a log function:
    ymax * np.log(band / xmin) / np.log(xmax / xmin)

    Parameters
    ----------
    dsm_ds : rasterio.dataset
    dtm_ds : rasterio.dataset
    meta : dict
    dtype : encoding type
    dsm_window : rasterio.Windows
    dtm_window : rasterio.Windows
    width : int
     the original width of patch
    height : int
     the original height of patch
    resampling : rasterio.enums.Resampling
     resampling method (billinear, cubic, etc.)

    Returns
    -------
    NDArray
     a NDArray containing the height coded in Byte (0..255)
    """

    if dsm_window is not None and dtm_window is not None:

        dsm_band = dsm_ds.read(1,
                               window=dsm_window,
                               out_shape=(1, height, width),
                               resampling=resampling)

        dsm_band = normalize_array_in(dsm_band,
                                      meta["dtype"],
                                      IMAGE_TYPE[meta["dtype"]][2])
        dtm_band = dtm_ds.read(1,
                               window=dtm_window,
                               out_shape=(1, height, width),
                               resampling=resampling)
        dtm_band = normalize_array_in(dtm_band,
                                      meta["dtype"],
                                      IMAGE_TYPE[meta["dtype"]][2])
    else:

        dsm_band = dsm_ds.read(1)
        dtm_band = dtm_ds.read(1)
        dsm_band = normalize_array_in(dsm_band,
                                      meta["dtype"],
                                      IMAGE_TYPE[meta["dtype"]][2])
        dtm_band = normalize_array_in(dtm_band,
                                      meta["dtype"],
                                      IMAGE_TYPE[meta["dtype"]][2])

    band = dsm_band - dtm_band

    # scaling by a factor 5 : 1pix = 1m -> 1pix = 20 cm, hence the max height is 50m (= 255pix)
    band *= 5
    lower_bound, upper_bound = 0.2, 255
    band[band < lower_bound] = lower_bound
    band[band > upper_bound] = upper_bound  # we apply a cutout over 50m

    return band.astype(dtype)


def set_afffine_transform_to_meta(center, meta):
    """Set the affine transform metadata for a given patch
    to georeference the patch.

    Parameters
    ----------
    center : pandas.core.series.Series
     a row from a pandas DataFrame
    meta : array
     metadata for the window raster

    Returns
    -------
    rasterio.Affine
     an updated Affine transform

    """
    width = meta["width"]
    height = meta["height"]
    affine: rasterio.Affine = meta["transform"]

    ul_x = center.x - (1/2 * width)
    ul_y = center.y + (1/2 * height)

    return rasterio.Affine(affine.a, affine.b, ul_y, affine.d, affine.e, ul_x)


def normalize_array_in(array, dtype, max_type_val):
    """ Normalize band based on the encoding type and the max value of the type
    example: to convert in uint16 type will be uint16 and max type value will be 65535

    Parameters
    ----------
    array : NdArray
     band to normalize
    dtype : Union[str, numpy.dtype, rastion.dtype]
     target data type
    max_type_val : Union[int, float]
     value

    Returns
    -------
    band : NdArray
     the band normalized in the targeted encoding type

    """

    array = array.astype(np.float64)
    LOGGER.debug(array.max())

    if float(array.max()) != float(0):

        array *= max_type_val / array.max()

    return array.astype(dtype)


def get_max_type(rasters):
    """Find the type of the patches generated

    Parameters
    ----------
    rasters : dict
     a dictionary of raster name with at least metadata path for each one

    Returns
    -------
    dtype : str
     encoding type for the patches
    """

    dtype = "uint8"

    for name, raster in rasters.items():

        with rasterio.open(raster["path"]) as src:

            if src.meta["dtype"] in IMAGE_TYPE.keys() and IMAGE_TYPE[src.meta["dtype"]][0] > IMAGE_TYPE[dtype][0]:

                dtype = src.meta["dtype"]

    return dtype
