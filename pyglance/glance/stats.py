#!/usr/bin/env python
# encoding: utf-8
"""
This module handles statistical analysis of data sets. The code present in
this module is based on previous versions of delta.py.

Created by evas Apr 2010.
Copyright (c) 2010 University of Wisconsin SSEC. All rights reserved.
"""

import glance.data  as dataobj
import glance.delta as delta

import numpy as np

# TODO, finish transitioning to classes

# TODO, I don't like this design, but it's what I could come up
# with for now. Reconsider this again later.
class StatisticalData (object) :
    """
    This class represents a set of statistical data generated from
    the examination of two data sets. This data set is relatively
    abstract. 
    
    All Statistics Data objects should have a title and be able to provide
    a dictionary of their statistics (see dictionary_form function) and
    a dictionary documenting their statistics.
    
    Child classes can include whatever actual statistics they like.
    """
    
    def __init__ (self) :
        """
        a minimal constructor that only sets the title
        """
        
        self.title = None
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        
        note: child classes should override this method
        """
        return { }
    
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        
        note: child classes should override this method
        """
        return { }

class MissingValueStatistics (StatisticalData) :
    """
    A class representing information about where fill values are found
    in a pair of data sets.
    
    includes the following statistics:
    
    a_missing_count         -    count of points that are missing in the a data set
    a_missing_fraction      - fraction of points that are missing in the a data set
    b_missing_count         -    count of points that are missing in the b data set
    b_missing_fraction      - fraction of points that are missing in the b data set
    common_missing_count    -    count of points that are missing in both data sets
    common_missing_fraction - fraction of points that are missing in both data sets
    """
    
    def __init__(self, diffInfoObject) :
        """
        build our fill value related statistics based on the comparison
        of two data sets
        """
        self.title = 'Missing Value Statistics'
        
        # pull out some masks for later use
        a_missing_mask = diffInfoObject.a_data_object.masks.missing_mask
        b_missing_mask = diffInfoObject.b_data_object.masks.missing_mask
        
        assert(a_missing_mask.shape == b_missing_mask.shape)
        
        # figure out some basic statistics
        self.a_missing_count      = np.sum(a_missing_mask)
        self.b_missing_count      = np.sum(b_missing_mask)
        self.common_missing_count = np.sum(a_missing_mask & b_missing_mask)
        
        # make the assumption that a and b are the same size and only use the size of a's mask
        total_num_values = a_missing_mask.size
        
        # figure out some fraction statistics
        self.a_missing_fraction      = float(self.a_missing_count)      / float(total_num_values)
        self.b_missing_fraction      = float(self.b_missing_count)      / float(total_num_values)
        self.common_missing_fraction = float(self.common_missing_count) / float(total_num_values)
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        """
        
        toReturn = {
                    'a_missing_count':         self.a_missing_count,
                    'a_missing_fraction':      self.a_missing_fraction,
                    'b_missing_count':         self.b_missing_count,
                    'b_missing_fraction':      self.b_missing_fraction,
                    'common_missing_count':    self.common_missing_count,
                    'common_missing_fraction': self.common_missing_fraction
                    }
        
        return toReturn
    
    # TODO, replace the giant doc dictionary with use of this method
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        """
        
        toReturn = {
                    'a_missing_count':         "number of values flagged missing in A",
                    'a_missing_fraction':      "fraction of values flagged missing in A",
                    'b_missing_count':         "number of values flagged missing in B",
                    'b_missing_fraction':      "fraction of values flagged missing in B",
                    'common_missing_count':    "number of missing values in common between A and B",
                    'common_missing_fraction': "fraction of missing values in common between A and B"
                    }
        
        return toReturn

class FiniteDataStatistics (StatisticalData) :
    """
    A class representing information about where finite values are found
    in a pair of data sets.
    
    includes the following statistics:
    
    a_finite_count              - the number   of finite data values in the a data set
    a_finite_fraction           - the fraction of finite data values in the a data set
    b_finite_count              - the number   of finite data values in the b data set
    b_finite_fraction           - the fraction of finite data values in the b data set
    common_finite_count         - the number   of finite values the two data sets have in common
    common_finite_fraction      - the fraction of finite values the two data sets have in common
    finite_in_only_one_count    - the number   of points that are finite in only one of the two sets
    finite_in_only_one_fraction - the fraction of points that are finite in only one of the two sets
    """
    
    def __init__(self, diffInfoObject) :
        """
        build our finite data related statistics based on the comparison
        of two data sets
        """
        self.title = 'Finite Data Statistics'
        
        # pull out some data we will use later
        a_is_finite_mask   = diffInfoObject.a_data_object.masks.valid_mask
        b_is_finite_mask   = diffInfoObject.b_data_object.masks.valid_mask
        common_ignore_mask = diffInfoObject.diff_data_object.masks.ignore_mask
        
        assert(a_is_finite_mask.shape == b_is_finite_mask.shape)
        assert(b_is_finite_mask.shape == common_ignore_mask.shape)
        
        # figure out some basic statistics
        self.a_finite_count = np.sum(a_is_finite_mask)
        self.b_finite_count = np.sum(b_is_finite_mask)
        self.common_finite_count = np.sum(a_is_finite_mask & b_is_finite_mask)
        # use an exclusive or to check which points are finite in only one of the two data sets
        self.finite_in_only_one_count = np.sum((a_is_finite_mask ^ b_is_finite_mask) & ~common_ignore_mask)
        
        # make the assumption that a and b are the same size and only use the size of a's mask
        total_num_values = a_is_finite_mask.size
        
        # calculate some fractional statistics
        self.a_finite_fraction           = float(self.a_finite_count)           / float(total_num_values)
        self.b_finite_fraction           = float(self.b_finite_count)           / float(total_num_values)
        self.common_finite_fraction      = float(self.common_finite_count)      / float(total_num_values)
        self.finite_in_only_one_fraction = float(self.finite_in_only_one_count) / float(total_num_values)
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        """
        
        toReturn = {
                    'a_finite_count':              self.a_finite_count,
                    'a_finite_fraction':           self.a_finite_fraction,
                    'b_finite_count':              self.b_finite_count,
                    'b_finite_fraction':           self.b_finite_fraction,
                    'common_finite_count':         self.common_finite_count,
                    'common_finite_fraction':      self.common_finite_fraction,
                    'finite_in_only_one_count':    self.finite_in_only_one_count,
                    'finite_in_only_one_fraction': self.finite_in_only_one_fraction,
                    }
        
        return toReturn
    
    # TODO, replace the giant doc dictionary with use of this method
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        """
        
        toReturn = {
                    'a_finite_count': "number of finite values in A",
                    'a_finite_fraction': "fraction of finite values in A (out of all data points in A)",
                    'b_finite_count': "number of finite values in B",
                    'b_finite_fraction': "fraction of finite values in B (out of all data points in B)",
                    'common_finite_count': "number of finite values in common between A and B",
                    'common_finite_fraction': "fraction of finite values in common between A and B",
                    'finite_in_only_one_count': "number of values that changed finite-ness between A and B; " +
                                                "only the common spatially valid area is considerd for this statistic",
                    'finite_in_only_one_fraction': "fraction of values that changed finite-ness between A and B; " +
                                                "only the common spatially valid area is considerd for this statistic"
                    }
        
        return toReturn

class NotANumberStatistics (StatisticalData) :
    """
    A class representing information about where non-finite values are found
    in a pair of data sets.
    
    includes the following statistics:
    
    a_nan_count         - the number   of non finite values that are present in the a data set
    a_nan_fraction      - the fraction of non finite values that are present in the a data set
    b_nan_count         - the number   of non finite values that are present in the b data set
    b_nan_fraction      - the fraction of non finite values that are present in the b data set
    common_nan_count    - the number   of non finite values that are shared between the data sets
    common_nan_fraction - the fraction of non finite values that are shared between the data sets
    """
    
    def __init__(self, diffInfoObject) :
        """
        build our nonfinite data related statistics based on the comparison
        of two data sets
        """
        self.title = 'NaN Statistics'
        
        # pull out some masks we will use
        a_nan_mask = diffInfoObject.a_data_object.masks.non_finite_mask
        b_nan_mask = diffInfoObject.b_data_object.masks.non_finite_mask
        
        assert(a_nan_mask.shape == b_nan_mask.shape)
        
        # get some basic statistics
        self.a_nan_count      = np.sum(a_nan_mask)
        self.b_nan_count      = np.sum(b_nan_mask)
        self.common_nan_count = np.sum(a_nan_mask & b_nan_mask)
        
        # make the assumption that a and b are the same size and only use the size of a
        total_num_values = a_nan_mask.size
        
        # calculate some fractional statistics
        self.a_nan_fraction      = float(self.a_nan_count)      / float(total_num_values)
        self.b_nan_fraction      = float(self.b_nan_count)      / float(total_num_values)
        self.common_nan_fraction = float(self.common_nan_count) / float(total_num_values)
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        """
        
        toReturn = {
                    'a_nan_count':         self.a_nan_count,
                    'a_nan_fraction':      self.a_nan_fraction,
                    'b_nan_count':         self.b_nan_count,
                    'b_nan_fraction':      self.b_nan_fraction,
                    'common_nan_count':    self.common_nan_count,
                    'common_nan_fraction': self.common_nan_fraction
                    }
        
        return toReturn
    
    # TODO, replace the giant doc dictionary with use of this method
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        """
        
        toReturn = {
                    'a_nan_count': "number of NaNs in A",
                    'a_nan_fraction': "fraction of NaNs in A",
                    'b_nan_count': "number of NaNs in B",
                    'b_nan_fraction': "fraction of NaNs in B",
                    'common_nan_count': "number of NaNs in common between A and B",
                    'common_nan_fraction': "fraction of NaNs in common between A and B"
                    }
        
        return toReturn

class GeneralStatistics (StatisticalData) :
    """
    A class representing general information about a pair of data sets.
    
    includes the following statistics:
    
    a_missing_value - the fill data value in the a set
    b_missing_value - the fill data value in the b set
    epsilon         - the fixed epsilon value
    epsilon_percent - the percentage of the a set that will be used for comparison
    max_a           - the maximum value in the a set
    max_b           - the maximum value in the b set
    min_a           - the minimum value in the a set
    min_b           - the minimum value in the b set
    num_data_points - the total number of data points in each of the sets
    shape           - the shape of each of the data sets
    spatially_invalid_pts_ignored_in_a - number of points corresponding to invalid lat/lon in a set
    spatially_invalid_pts_ignored_in_b - number of points corresponding to invalid lat/lon in b set
    """
    
    def __init__(self, diffInfoObject) :
        """
        build our general statistics based on the comparison
        of two data sets
        """
        self.title = 'NaN Statistics'
        
        # pull out some masks for later use
        a_missing_mask   = diffInfoObject.a_data_object.masks.missing_mask
        b_missing_mask   = diffInfoObject.b_data_object.masks.missing_mask
        ignore_in_a_mask = diffInfoObject.a_data_object.masks.ignore_mask
        ignore_in_b_mask = diffInfoObject.b_data_object.masks.ignore_mask
        good_in_a_mask   = diffInfoObject.a_data_object.masks.valid_mask
        good_in_b_mask   = diffInfoObject.b_data_object.masks.valid_mask
        
        assert(a_missing_mask.shape   ==   b_missing_mask.shape)
        assert(b_missing_mask.shape   == ignore_in_a_mask.shape)
        assert(ignore_in_a_mask.shape == ignore_in_b_mask.shape)
        assert(ignore_in_b_mask.shape ==   good_in_a_mask.shape)
        assert(good_in_a_mask.shape   ==   good_in_b_mask.shape)
        
        # get the number of data points
        total_num_values = a_missing_mask.size
        
        # fill in our statistics
        self.a_missing_value = diffInfoObject.a_data_object.fill_value
        self.b_missing_value = diffInfoObject.b_data_object.fill_value
        self.epsilon         = diffInfoObject.epsilon_value
        self.epsilon_percent = diffInfoObject.epsilon_percent
        self.max_a           = delta.max_with_mask(diffInfoObject.a_data_object.data, good_in_a_mask)
        self.min_a           = delta.min_with_mask(diffInfoObject.a_data_object.data, good_in_a_mask)
        self.max_b           = delta.max_with_mask(diffInfoObject.b_data_object.data, good_in_b_mask)
        self.min_b           = delta.min_with_mask(diffInfoObject.b_data_object.data, good_in_b_mask)
        self.num_data_points = total_num_values
        self.shape           = a_missing_mask.shape
        # also calculate the invalid points
        self.spatially_invalid_pts_ignored_in_a = np.sum(ignore_in_a_mask)
        self.spatially_invalid_pts_ignored_in_b = np.sum(ignore_in_b_mask)
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        """
        
        toReturn = {
                    'a_missing_value': self.a_missing_value,
                    'b_missing_value': self.b_missing_value,
                    'epsilon':         self.epsilon,
                    'epsilon_percent': self.epsilon_percent,
                    'max_a':           self.max_a,
                    'max_b':           self.max_b,
                    'min_a':           self.min_a,
                    'min_b':           self.min_b,
                    'num_data_points': self.num_data_points,
                    'shape':           self.shape,
                    'spatially_invalid_pts_ignored_in_a': self.spatially_invalid_pts_ignored_in_a,
                    'spatially_invalid_pts_ignored_in_b': self.spatially_invalid_pts_ignored_in_b
                    }
        
        return toReturn
    
    # TODO, replace the giant doc dictionary with use of this method
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        """
        
        toReturn = {
                    'a_missing_value': 'the value that is considered \"missing\" data when it is found in A',
                    'b_missing_value': 'the value that is considered \"missing\" data when it is found in B',
                    'epsilon': 'amount of difference between matching data points in A and B that is considered acceptable',
                    'epsilon_percent': 'the percentage of difference (of A\'s value) that is acceptable between A and B (optional)',
                    'max_a': 'the maximum finite, non-missing value found in A',
                    'max_b': 'the maximum finite, non-missing value found in B',
                    'min_a': 'the minimum finite, non-missing value found in A',
                    'min_b': 'the minimum finite, non-missing value found in B',
                    'num_data_points': "number of data values in A",
                    'shape': "shape of A",
                    'spatially_invalid_pts_ignored_in_a': 'number of points with invalid latitude/longitude information in A that were' +
                                                            ' ignored for the purposes of data analysis and presentation',
                    'spatially_invalid_pts_ignored_in_b': 'number of points with invalid latitude/longitude information in B that were' +
                                                            ' ignored for the purposes of data analysis and presentation',
                    }
        
        return toReturn

class NumericalComparisonStatistics (StatisticalData) :
    """
    A class representing more complex comparisons between a pair of data sets.
    
    includes the following statistics:
    
    correlation                   - the Pearson correlation r-coefficient from comparing finite values of the sets
    r_squared_correlation         - the square of the correlation
    diff_outside_epsilon_count    - the number   of points that fall outside the acceptable epsilon settings
    diff_outside_epsilon_fraction - the fraction of points that fall outside the acceptable epsilon settings
    perfect_match_count           - the number   of points that match perfectly between the sets
    perfect_match_fraction        - the fraction of points that match perfectly between the sets
    trouble_points_count          - the number   of points that have possible issues according to the current analysis
    trouble_points_fraction       - the fraction of points that have possible issues according to the current analysis
    
    It may also contain additional statistics. This is indicated by the does_include_simple boolean.
    The possible additional statistics include:
    
    rms_diff    -  the root mean squared of the absolute difference between the two data sets
    std_diff    - the standard deviation of the absolute difference between the two data sets
    mean_diff   -               the mean of the absolute difference between the two data sets
    median_diff -             the median of the absolute difference between the two data sets
    max_diff    -            the maximum of the absolute difference between the two data sets
    
    These statistics can also be generated separately in dictionary form by calling the
    basic_analysis method on this class.
    """
    
    def __init__(self, diffInfoObject, include_basic_analysis=True) :
        """
        build our comparison statistics based on the comparison
        of two data sets
        
        the include_basic_analysis flag indicates whether the statistics generated by the
        basic_analysis method should also be generated
        """
        self.title = 'Numerical Comparison Statistics'
        
        # pull out some info we will use later
        valid_in_both        = diffInfoObject.diff_data_object.masks.valid_mask
        outside_epsilon_mask = diffInfoObject.diff_data_object.masks.outside_epsilon_mask
        trouble_mask         = diffInfoObject.diff_data_object.masks.trouble_mask
        aData                = diffInfoObject.a_data_object.data
        bData                = diffInfoObject.b_data_object.data
        
        assert (valid_in_both.shape        == outside_epsilon_mask.shape)
        assert (outside_epsilon_mask.shape == trouble_mask.shape)
        assert (trouble_mask.shape         == aData.shape)
        assert (aData.shape                == bData.shape)
        
        # fill in some simple statistics
        self.diff_outside_epsilon_count = np.sum(outside_epsilon_mask)
        self.perfect_match_count        = NumericalComparisonStatistics._get_num_perfect(aData, bData,
                                                                                         goodMask=valid_in_both)
        self.correlation                = delta.compute_correlation(aData, bData, valid_in_both)
        self.r_squared_correlation      = self.correlation * self.correlation
        self.trouble_points_count       = np.sum(trouble_mask)
        
        # we actually want the total number of _finite_ values rather than all the data
        total_num_finite_values = np.sum(valid_in_both)
        
        # calculate some more complex statistics
        self.trouble_points_fraction = float(self.trouble_points_count) / float(aData.size)
        # be careful not to divide by zero if we don't have finite data
        if total_num_finite_values > 0 :
            self.diff_outside_epsilon_fraction = float(self.diff_outside_epsilon_count) / float(total_num_finite_values)
            self.perfect_match_fraction        = float(self.perfect_match_count)        / float(total_num_finite_values)
        else:
            self.diff_outside_epsilon_fraction = 0.0
            self.perfect_match_fraction        = 0.0
        
        # if desired, do the basic analysis
        self.does_include_simple = include_basic_analysis
        if (include_basic_analysis) :
            basic_dict = NumericalComparisonStatistics.basic_analysis(diffInfoObject.diff_data_object.data,
                                                                      valid_in_both)
            self.rms_diff      = basic_dict['rms_diff']
            self.std_diff      = basic_dict['std_diff']
            self.mean_diff     = basic_dict['mean_diff']
            self.median_diff   = basic_dict['median_diff']
            self.max_diff      = basic_dict['max_diff']
            self.temp_analysis = basic_dict
    
    def dictionary_form(self) :
        """
        get a dictionary form of the statistics
        """
        
        toReturn = {
                    'correlation':                   self.correlation,
                    'r-squared correlation':         self.r_squared_correlation,
                    'diff_outside_epsilon_count':    self.diff_outside_epsilon_count,
                    'diff_outside_epsilon_fraction': self.diff_outside_epsilon_fraction,
                    'perfect_match_count':           self.perfect_match_count,
                    'perfect_match_fraction':        self.perfect_match_fraction,
                     'trouble_points_count':         self.trouble_points_count, 
                     'trouble_points_fraction':      self.trouble_points_fraction
                    }
        toReturn.update(self.temp_analysis)
        
        return toReturn
    
    # TODO, replace the giant doc dictionary with use of this method
    def doc_strings(self) :
        """
        get documentation strings that match the
        dictionary form of the statistics
        """
        
        toReturn = {
                    'correlation': "Pearson correlation r-coefficient (0.0-1.0) for finite values of A and B",
                    'diff_outside_epsilon_count': "number of finite differences falling outside acceptable epsilon definitions; " +
                                            "note: this value includes data excluded by both epsilon and epsilon_percent if " +
                                            "both have been defined",
                    'diff_outside_epsilon_fraction': "fraction of finite differences falling outside acceptable epsilon " +
                                            "definitions (out of common_finite_count)",
                    'max_diff': "Maximum difference of finite values",
                    'mean_diff': "mean difference of finite values",
                    'median_diff': "median difference of finite values",
                    'perfect_match_count': "number of perfectly matched finite data points between A and B",
                    'perfect_match_fraction': "fraction of finite values perfectly matching between A and B (out of common_finite_count)",
                    'rms_diff': "root mean square (RMS) difference of finite values",
                    'r-squared correlation': "the square of the r correlation (see correlation)",
                    'std_diff': "standard deviation of difference of finite values",
                    'trouble_points_count': 'number of points that differ in finite/missing status between the input data sets A and B,' +
                                            ' or are unacceptable when compared according to the current epsilon definitions',
                    'trouble_points_fraction': 'fraction of points that differ in finite/missing status between the input data sets A and B,' +
                                            ' or are unacceptable when compared according to the current epsilon definitions',
                    }
        
        return toReturn
    
    @staticmethod
    def basic_analysis(diffData, valid_mask):
        """
        do some very minimal analysis of the differences
        """
        
        # if all the data is invalid,
        # we can't do any of these forms of statistical analysis
        if np.sum(valid_mask) <= 0 :
            return { }
        
        # calculate our statistics
        absDiffData = abs(diffData)
        root_mean_square_value = delta.calculate_root_mean_square(diffData, valid_mask)
        return {    'rms_diff':                root_mean_square_value, 
                    'std_diff':       np.std(absDiffData[valid_mask]), 
                    'mean_diff':     np.mean(absDiffData[valid_mask]), 
                    'median_diff': np.median(absDiffData[valid_mask]),
                    'max_diff':       np.max(absDiffData[valid_mask])
                    }
    
    @staticmethod
    def _get_num_perfect(aData, bData, goodMask=None):
        """
        get the number of data points where
        the value in A perfectly matches the value in B
        """
        numPerfect = 0
        if not (goodMask is None) :
            numPerfect = np.sum(aData[goodMask] == bData[goodMask])
        else :
            numPerfect = np.sum(aData == bData)
        return numPerfect

# --------------------- general statistics methods ------------------

def summarize(a, b, epsilon=0.,
              (a_missing_value, b_missing_value)=(None,None),
              ignoreInAMask=None, ignoreInBMask=None,
              epsilonPercent=None):
    """return dictionary of statistics dictionaries
    stats not including 'nan' in name exclude nans in either arrays
    """
    # diff our two data sets
    aDataObject = dataobj.DataObject(a, fillValue=a_missing_value, ignoreMask=ignoreInAMask)
    bDataObject = dataobj.DataObject(b, fillValue=b_missing_value, ignoreMask=ignoreInBMask)
    diffInfo = dataobj.DiffInfoObject(aDataObject, bDataObject,
                                      epsilonValue=epsilon, epsilonPercent=epsilonPercent) 
    
    general_stats    = GeneralStatistics(diffInfo)
    comparison_stats = NumericalComparisonStatistics(diffInfo)
    nan_stats        = NotANumberStatistics(diffInfo)
    missing_stats    = MissingValueStatistics(diffInfo)
    finite_stats     = FiniteDataStatistics(diffInfo)
    
    out = {}
    out[nan_stats.title]        = nan_stats.dictionary_form()
    out[missing_stats.title]    = missing_stats.dictionary_form()
    out[finite_stats.title]     = finite_stats.dictionary_form()
    out[comparison_stats.title] = comparison_stats.dictionary_form()
    out[general_stats.title]    = general_stats.dictionary_form()
    
    return out

# -------------------------- documentation -----------------------------

STATISTICS_DOC = {  'general': "Finite values are non-missing and finite (not NaN or +-Inf); fractions are out of all data, " +
                               "both finite and not, unless otherwise specified",
                    
                    # general statistics
                    'a_missing_value': 'the value that is considered \"missing\" data when it is found in A',
                    'b_missing_value': 'the value that is considered \"missing\" data when it is found in B',
                    'epsilon': 'amount of difference between matching data points in A and B that is considered acceptable',
                    'epsilon_percent': 'the percentage of difference (of A\'s value) that is acceptable between A and B (optional)',
                    'max_a': 'the maximum finite, non-missing value found in A',
                    'max_b': 'the maximum finite, non-missing value found in B',
                    'min_a': 'the minimum finite, non-missing value found in A',
                    'min_b': 'the minimum finite, non-missing value found in B',
                    'num_data_points': "number of data values in A",
                    'shape': "shape of A",
                    'spatially_invalid_pts_ignored_in_a': 'number of points with invalid latitude/longitude information in A that were' +
                                                            ' ignored for the purposes of data analysis and presentation',
                    'spatially_invalid_pts_ignored_in_b': 'number of points with invalid latitude/longitude information in B that were' +
                                                            ' ignored for the purposes of data analysis and presentation',
                    
                    # finite data stats descriptions
                    'a_finite_count': "number of finite values in A",
                    'a_finite_fraction': "fraction of finite values in A (out of all data points in A)",
                    'b_finite_count': "number of finite values in B",
                    'b_finite_fraction': "fraction of finite values in B (out of all data points in B)",
                    'common_finite_count': "number of finite values in common between A and B",
                    'common_finite_fraction': "fraction of finite values in common between A and B",
                    'finite_in_only_one_count': "number of values that changed finite-ness between A and B; " +
                                                "only the common spatially valid area is considerd for this statistic",
                    'finite_in_only_one_fraction': "fraction of values that changed finite-ness between A and B; " +
                                                "only the common spatially valid area is considerd for this statistic",
                    
                    # missing data value statistics
                    'a_missing_count': "number of values flagged missing in A",
                    'a_missing_fraction': "fraction of values flagged missing in A",
                    'b_missing_count': "number of values flagged missing in B",
                    'b_missing_fraction': "fraction of values flagged missing in B",
                    'common_missing_count': "number of missing values in common between A and B",
                    'common_missing_fraction': "fraction of missing values in common between A and B",
                    
                    # NaN related statistics
                    'a_nan_count': "number of NaNs in A",
                    'a_nan_fraction': "fraction of NaNs in A",
                    'b_nan_count': "number of NaNs in B",
                    'b_nan_fraction': "fraction of NaNs in B",
                    'common_nan_count': "number of NaNs in common between A and B",
                    'common_nan_fraction': "fraction of NaNs in common between A and B",
                    
                    # Numerical comparison statistics
                    'correlation': "Pearson correlation r-coefficient (0.0-1.0) for finite values of A and B",
                    'diff_outside_epsilon_count': "number of finite differences falling outside epsilon",
                    'diff_outside_epsilon_fraction': "fraction of finite differences falling outside epsilon (out of common_finite_count)",
                    'max_diff': "Maximum difference of finite values",
                    'mean_diff': "mean difference of finite values",
                    'median_diff': "median difference of finite values",
                    'perfect_match_count': "number of perfectly matched finite data points between A and B",
                    'perfect_match_fraction': "fraction of finite values perfectly matching between A and B (out of common_finite_count)",
                    'rms_diff': "root mean square (RMS) difference of finite values",
                    'r-squared correlation': "the square of the r correlation (see correlation)",
                    'std_diff': "standard deviation of difference of finite values",
                    'trouble_points_count': 'number of points that differ in finite/missing status between the input data sets A and B,' +
                                            ' or are unacceptable when compared according to the current epsilon value',
                    'trouble_points_fraction': 'fraction of points that differ in finite/missing status between the input data sets A and B,' +
                                            ' or are unacceptable when compared according to the current epsilon value',
                    
                    # note: the statistics described below may no longer be generated?
                    'mean_percent_change': "Percent change from A to B for finite values, averaged",
                    'max_percent_change': "Percent change from A to B for finite values, maximum value"
                    
                    }
STATISTICS_DOC_STR = '\n'.join( '%s:\n    %s' % x for x in sorted(list(STATISTICS_DOC.items())) ) + '\n'

if __name__=='__main__':
    import doctest
    doctest.testmod()