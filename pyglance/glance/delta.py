#!/usr/bin/env python
# encoding: utf-8
"""
Routines to do assorted difference and comparison calculations and statistics

Created by rayg Apr 2009.
Copyright (c) 2009 University of Wisconsin SSEC. All rights reserved.
"""

import logging
import numpy as np
from numpy import *
from scipy.stats import pearsonr

compute_r = pearsonr

LOG = logging.getLogger(__name__)

# Upcasts to be used in difference computation to avoid overflow. Currently only unsigned
# ints are upcast.
# FUTURE: handle uint64s as well (there is no int128, so might have to detect overflow)
datatype_upcasts = {
    uint8: int16,
    uint16: int32,
    uint32: int64
    }

# TODO, where is this being used?
def _missing(x, missing_value=None):
    if missing_value is not None:
        return isnan(x) | (x==missing_value)
    return isnan(x)

def diff(aData, bData, epsilon=0.,
         (a_missing_value, b_missing_value)=(None, None),
         (ignore_mask_a, ignore_mask_b)=(None, None)):
    """
    take two arrays of similar size and composition
    if an ignoreMask is passed in values in the mask will not be analysed to
    form the various return masks and the corresponding spots in the
    "difference" return data array will contain fill values (selected
    based on data type).
    
    return difference array filled with fill data where differences aren't valid,
    good mask where values are finite in both a and b
    trouble mask where missing values or nans don't match or delta > epsilon
    (a-notfinite-mask, b-notfinite-mask)
    (a-missing-mask, b-missing-mask)
    """
    shape = aData.shape
    assert(bData.shape==shape)
    assert(can_cast(aData.dtype, bData.dtype) or can_cast(bData.dtype, aData.dtype))
    
    # if the ignore masks do not exist, set them to include none of the data
    if (ignore_mask_a is None) :
        ignore_mask_a = zeros(shape,dtype=bool)
    if (ignore_mask_b is None) :
        ignore_mask_b = zeros(shape,dtype=bool)
    
    # deal with the basic masks
    a_not_finite_mask, b_not_finite_mask = ~isfinite(aData) & ~ignore_mask_a, ~isfinite(bData) & ~ignore_mask_b
    a_missing_mask, b_missing_mask = zeros(shape,dtype=bool), zeros(shape,dtype=bool)
    # if we were given missing values, mark where they are in the data
    if a_missing_value is not None:
        a_missing_mask[aData == a_missing_value] = True
        a_missing_mask[ignore_mask_a] = False # don't analyse the ignored values
    if b_missing_value is not None:
        b_missing_mask[bData == b_missing_value] = True
        b_missing_mask[ignore_mask_b] = False # don't analyse the ignored values
    
    # build the comparison data that includes the "good" values
    valid_in_a_mask = ~(a_not_finite_mask | a_missing_mask | ignore_mask_a)
    valid_in_b_mask = ~(b_not_finite_mask | b_missing_mask | ignore_mask_b)
    valid_in_both = valid_in_a_mask & valid_in_b_mask
    
    # figure out our shared data type
    sharedType = aData.dtype
    if (aData.dtype is not bData.dtype) :
        sharedType = common_type(aData, bData)

    # upcast if needed to avoid overflow in difference operation
    if sharedType in datatype_upcasts:
        sharedType = datatype_upcasts[sharedType]

    LOG.debug('Shared data type that will be used for diff comparison: ' + str(sharedType))
    
    # construct our diff'ed array
    raw_diff = zeros(shape, dtype=sharedType) #empty_like(aData)
    
    fill_data_value = select_fill_data(sharedType)
    
    LOG.debug('current fill data value: ' + str(fill_data_value))
    
    raw_diff[~valid_in_both] = fill_data_value # throw away invalid data

    # compute difference, using shared type in computation
    raw_diff[valid_in_both] = bData[valid_in_both].astype(sharedType) - aData[valid_in_both].astype(sharedType)
        
    # the valid data which is too different between the two sets according to the given epsilon
    outside_epsilon_mask = (abs(raw_diff) > epsilon) & valid_in_both
    # trouble points = mismatched nans, mismatched missing-values, differences that are too large 
    trouble_pt_mask = (a_not_finite_mask ^ b_not_finite_mask) | (a_missing_mask ^ b_missing_mask) | outside_epsilon_mask
    
    return raw_diff, valid_in_both, (valid_in_a_mask, valid_in_b_mask), trouble_pt_mask, outside_epsilon_mask,  \
           (a_not_finite_mask, b_not_finite_mask), (a_missing_mask, b_missing_mask), (ignore_mask_a, ignore_mask_b)

def select_fill_data(dTypeValue) :
    """
    select a fill data value based on the type of data that is being
    inspected/changed
    """
    
    fill_value_to_return = None
    
    if issubdtype(dTypeValue, np.float) or issubdtype(dTypeValue, np.complex) :
        fill_value_to_return = nan
    elif issubdtype(dTypeValue, np.int) :
        fill_value_to_return = np.iinfo(dTypeValue).min
    elif issubdtype(dTypeValue, np.bool) :
        fill_value_to_return = True
    elif ((dTypeValue is np.uint8)  or
          (dTypeValue is np.uint16) or
          (dTypeValue is np.uint32) or
          (dTypeValue is np.uint64)) :
        fill_value_to_return = np.iinfo(dTypeValue).max
    
    return fill_value_to_return

def corr(x,y,mask):
    "compute correlation coefficient"
    gf = mask.flatten()
    xf = x.flatten()[gf]
    yf = y.flatten()[gf]
    assert(sum(~isfinite(yf))==0)
    assert(sum(~isfinite(xf))==0)
    # don't try to build a correlation if
    # masking left us with insufficient data
    # to do so
    if (xf.size < 2) or (yf.size < 2) :
        return nan
    return compute_r(xf,yf)[0]

def convert_mag_dir_to_U_V_vector(magnitude_data, direction_data, invalidMask=None):
    """
    This method is intended to convert magnitude and direction data into (U, V) vector data.
    An invalid mask may be given if some of the points in the set should be masked out.
    
    TODO, this method is not fully tested
    """
    
    if invalidMask is None :
        invalidMask = zeros(magnitude_data.shape, dtype=bool)
    
    new_direction_data = direction_data[:] + 180
    
    print ("direction data: " + str(new_direction_data[~invalidMask]))
    
    uData = zeros(magnitude_data.shape, dtype=float)
    uData[invalidMask]  = nan
    uData[~invalidMask] = magnitude_data[~invalidMask] * np.sin (deg2rad(new_direction_data[~invalidMask]))
    
    vData = zeros(magnitude_data.shape, dtype=float)
    vData[invalidMask]  = nan
    vData[~invalidMask] = magnitude_data[~invalidMask] * np.cos (deg2rad(new_direction_data[~invalidMask]))
    
    return uData, vData

# a method to make a list of index numbers for reordering a multi-dimensional array
def _make_new_index_list(numberOfIndexes, firstIndexNumber=0, lastIndexNumber=None) :
    """
    the first and last index numbers represent the dimensions you want to be first and last (respectively)
    when the list is reordered; any other indexes will retain their relative ordering
    
    newIndexList = _make_new_index_list(numIndexes, binIndex, tupleIndex)
    """
    
    if lastIndexNumber is None:
        lastIndexNumber = numberOfIndexes - 1
    
    newIndexList = range(numberOfIndexes)
    maxSpecial   = max(firstIndexNumber, lastIndexNumber)
    minSpecial   = min(firstIndexNumber, lastIndexNumber)
    del(newIndexList[maxSpecial])
    del(newIndexList[minSpecial])
    newIndexList = [firstIndexNumber] + newIndexList + [lastIndexNumber]
    
    return newIndexList

def reorder_for_bin_tuple (data, binIndexNumber, tupleIndexNumber) :
    """
    reorder the data given so that the bin index is first, the tuple index is last,
    and any additional dimensions are flattened into a middle "case" index
    
    the reordered data and the shape of flattened case indexes will be returned
    (note if the original data was only 2 dimensional, None will be returned for the
    shape of the flattened case indexes, since there were no other dimensions to flatten)
    """
    
    # put the bin and tuple dimensions in the correct places
    newIndexList = _make_new_index_list(len(data.shape), binIndexNumber, tupleIndexNumber)
    newData = data.transpose(newIndexList)
    
    # get the shape information on the internal dimensions we're going to combine
    caseOriginalShape = newData.shape[1:-1]
    
    # combine the internal dimensions, to figure out what shape things
    # will be with the flattened cases
    sizeAfterFlattened = np.multiply.accumulate(caseOriginalShape)[-1]
    newShape = (newData.shape[0], sizeAfterFlattened, newData.shape[-1])
    
    # flatten the case dimensions
    newData = newData.reshape(newShape)
    
    # TODO, remove once this is tested
    #print ('original data shape: ' + str(data.shape))
    #print ('original case shape: ' + str(caseOriginalShape))
    #print ('new data shape:      ' + str(newData.shape))
    
    return newData, caseOriginalShape

def determine_case_indecies (flatIndex, originalCaseShape) :
    """
    determine the original indexes of the case
    given the flat index number and the original shape
    
    Note: this method is very memory inefficent
    TODO, find a better way of doing this? does numpy guarantee reshaping strategy?
    """
    
    # create a long flat array with the contents being the index number
    numCases = np.multiply.accumulate(originalCaseShape)[-1]
    temp = np.array(range(numCases))
    
    # reshape the flat array back to the original shape
    # then figure out where our index went
    temp = temp.reshape(originalCaseShape)
    positionOfIndex = np.where(temp == flatIndex)
    
    del temp
    
    return positionOfIndex

def calculate_root_mean_square (data, goodMask=None) :
    """
    calculate the root mean square of the data,
    possibly selecting only the points in the given
    goodMask, if no mask is given, all points will
    be used
    """
    if goodMask is None:
        goodMask = np.ones(data.shape, dtype=bool)
    
    rootMeanSquare = sqrt( sum( data[goodMask] ** 2 ) / sum( goodMask ) )
    
    return rootMeanSquare

# get the min, ignoring the stuff in mask
def min_with_mask(data, mask=None) :
    
    if (mask is None) and (type(data) is numpy.ma) :
        mask = ~data.mask
    if mask is None :
        mask = np.zeros(data.shape, dtype=bool)
    
    temp = data[~mask]
    toReturn = None
    if len(temp) > 0 :
        toReturn = temp[temp.argmin()]
    return toReturn

# get the max, ignoring the stuff in mask
def max_with_mask(data, mask=None) :
    
    if (mask is None) and (type(data) is numpy.ma) :
        mask = ~data.mask
    if mask is None :
        mask = np.zeros(data.shape, dtype=bool)
    
    temp = data[~mask]
    toReturn = None
    if len(temp) > 0 :
        toReturn = temp[temp.argmax()]
    return toReturn

if __name__=='__main__':
    import doctest
    doctest.testmod()
