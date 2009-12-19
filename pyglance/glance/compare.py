#!/usr/bin/env python
# encoding: utf-8
"""

Top-level routines to compare two files.


Created by rayg Apr 2009.
Copyright (c) 2009 University of Wisconsin SSEC. All rights reserved.
"""

import os, sys, logging, re, subprocess, datetime
import imp as imp
from pprint import pprint, pformat
from numpy import *
import pkg_resources
from pycdf import CDFError

import glance.io as io
import glance.delta as delta
import glance.plot as plot
import glance.plotcreatefns as plotcreate
import glance.report as report

from urllib import quote

LOG = logging.getLogger(__name__)

# these are the built in defaults for the settings
glance_setting_defaults = {'shouldIncludeReport':       True,
                           'shouldIncludeImages':       False,
                           'doFork':                    False,
                           'useThreadsToControlMemory': False,
                           'useSharedRangeForOriginal': False,
                           'noLonLatVars':              False}

# these are the built in longitude/latitude defaults
glance_lon_lat_defaults = {'longitude': 'pixel_longitude',
                           'latitude':  'pixel_latitude',
                           'lon_lat_epsilon': 0.0,
                           'data_filter_function_lon_in_a': None,
                           'data_filter_function_lat_in_a': None,
                           'data_filter_function_lon_in_b': None,
                           'data_filter_function_lat_in_b': None
                           }

# these are the built in default settings for the variable analysis
glance_analysis_defaults = {'epsilon': 0.0,
                            'missing_value': None,
                            'epsilon_failure_tolerance': 0.0, 
                            'nonfinite_data_tolerance':  0.0 
                            }

def _cvt_names(namelist, epsilon, missing):
    """"if variable names are of the format name:epsilon, yield name,epsilon, missing
        otherwise yield name,default-epsilon,default-missing
    """
    for name in namelist:
        if ':' not in name:
            yield name, epsilon
        else:
            n,e,m = name.split(':')
            if not e: e = epsilon
            else: e = float(e)
            if not m: m = missing
            else: m = float(m)
            yield n, e, m

def _parse_varnames(names, terms, epsilon=0.0, missing=None):
    """filter variable names and substitute default epsilon and missing settings if none provided
    returns name,epsilon,missing triples
    >>> _parse_varnames( ['foo','bar', 'baz', 'zoom', 'cat'], ['f..:0.5:-999', 'ba.*:0.001', 'c.t::-9999'], 1e-7 )
    set([('foo', 0.5, -999.0), ('cat', 9.9999999999999995e-08, -9999.0), ('bar', 0.001, None), ('baz', 0.001, None)])
    """
    terms = [x.split(':') for x in terms]
    terms = [(re.compile(x[0]).match,x[1:]) for x in terms]
    def _cvt_em(eps=None, mis=None):
        eps = float(eps) if eps else epsilon
        mis = float(mis) if mis else missing
        return eps, mis
    sel = [ ((x,)+_cvt_em(*em)) for x in names for (t,em) in terms if t(x) ]
    return set(sel)

def _setup_file(fileNameAndPath, prefexText='') :
    '''
    open the provided file name/path and extract information on the md5sum and last modification time
    optional prefext text may be passed in for informational output formatting
    '''
    # some info to return
    fileInfo = {'path': fileNameAndPath}
    
    # check to see if the path exists to be opened
    if not (os.path.exists(fileNameAndPath)) :
        LOG.warn("Requested file " + fileNameAndPath + " could not be opened because it does not exist.")
        return None, fileInfo
    
    # open the file
    LOG.info(prefexText + "opening " + fileNameAndPath)
    fileNameAndPath = os.path.abspath(os.path.expanduser(fileNameAndPath))
    LOG.debug("User provided path after normalization and user expansion: " + fileNameAndPath)
    fileObject = io.open(fileNameAndPath)
    
    # get the file md5sum
    tempSubProcess = subprocess.Popen("md5sum \'" + fileNameAndPath + "\'", shell=True, stdout=subprocess.PIPE)
    fileInfo['md5sum'] = tempSubProcess.communicate()[0].split()[0]
    LOG.info(prefexText + "file md5sum: " + str(fileInfo['md5sum']))
    
    # get the last modified stamp
    statsForFile = os.stat(fileNameAndPath)
    fileInfo['lastModifiedTime'] = datetime.datetime.fromtimestamp(statsForFile.st_mtime).ctime() # should time zone be forced?
    LOG.info (prefexText + "file was last modified: " + fileInfo['lastModifiedTime'])
    
    return fileObject, fileInfo

def _check_file_names(fileAObject, fileBObject) :
    """
    get information about the names in the two files and how they compare to each other
    """
    # get information about the variables stored in the files
    aNames = set(fileAObject())
    bNames = set(fileBObject())
    
    # get the variable names they have in common
    commonNames = aNames.intersection(bNames)
    # which names are unique to only one of the two files?
    uniqueToANames = aNames - commonNames
    uniqueToBNames = bNames - commonNames
    
    return {'sharedVars': commonNames,  'uniqueToAVars': uniqueToANames, 'uniqueToBVars': uniqueToBNames}

def _resolve_names(fileAObject, fileBObject, defaultValues,
                   requestedNames, usingConfigFileFormat=False) :
    """
    figure out which names the two files share and which are unique to each file, as well as which names
    were requested and are in both sets
    
    usingConfigFileFormat signals whether the requestedNames parameter will be in the form of the inputed
    names from the command line or a more complex dictionary holding information about the names read in
    from a configuration file
    
    Note: if we ever need a variable with different names in file A and B to be comparable, this logic
    will need to be changed.
    """
    # look at the names present in the two files and compare them
    nameComparison = _check_file_names(fileAObject, fileBObject)
    
    # figure out which set should be selected based on the user requested names
    fileCommonNames = nameComparison['sharedVars']
    finalNames = {}
    if (usingConfigFileFormat) :
        
        # if the user didn't ask for any, try everything
        if (len(requestedNames) is 0) :
            finalFromCommandLine = _parse_varnames(fileCommonNames, ['.*'],
                                                   defaultValues['epsilon'], defaultValues['missing_value'])
            for name, epsilon, missing in finalFromCommandLine :
                # we'll use the variable's name as the display name for the time being
                finalNames[name] = {}
                # make sure we pick up any other controlling defaults
                finalNames[name].update(defaultValues) 
                # but override the values that would have been determined by _parse_varnames
                finalNames[name]['variable_name'] = name
                finalNames[name]['epsilon'] = epsilon
                
                # load the missing value if it was not provided
                missing, missing_b = _get_missing_values_if_needed((fileAObject, fileBObject), name,
                                                                   missing_value_A=missing, missing_value_B=missing)
                finalNames[name]['missing_value'] = missing 
                finalNames[name]['missing_value_alt_in_b'] = missing_b
                
        # otherwise just do the ones the user asked for
        else : 
            # check each of the names the user asked for to see if it is either in the list of common names
            # or, if the user asked for an alternate name mapping in file B, if the two mapped names are in
            # files A and B respectively
            for dispName in requestedNames :
                
                # hang on to info on the current variable
                currNameInfo = requestedNames[dispName] 
                
                # get the variable name 
                if 'variable_name' in currNameInfo :
                    name = currNameInfo['variable_name']
                    name_b = name
                    
                    if ('alternate_name_in_B' in currNameInfo) :
                        name_b = currNameInfo['alternate_name_in_B']
                    
                    if ( (name in fileCommonNames) and (not currNameInfo.has_key('alternate_name_in_B')) ) or \
                            ( (currNameInfo.has_key('alternate_name_in_B') and
                              ((name   in nameComparison['uniqueToAVars']) or (name   in fileCommonNames))  and
                              ((name_b in nameComparison['uniqueToBVars']) or (name_b in fileCommonNames))) ) :
                        finalNames[dispName] = defaultValues.copy() 
                        finalNames[dispName]['display_name'] = dispName
                        finalNames[dispName].update(currNameInfo)
                        
                        # load the missing value if it was not provided
                        missing = finalNames[dispName]['missing_value']
                        if ('missing_value_alt_in_b' in finalNames[dispName]) :
                            missing_b = finalNames[dispName]['missing_value_alt_in_b']
                        else :
                            missing_b = missing
                        finalNames[dispName]['missing_value'], finalNames[dispName]['missing_value_alt_in_b'] = \
                                    _get_missing_values_if_needed((fileAObject, fileBObject), name, name_b,
                                                                  missing, missing_b)
                        
                else :
                    LOG.warn('No technical variable name was given for the entry described as "' + dispName + '". ' +
                             'Skipping this variable.')
    else:
        # format command line input similarly to the stuff from the config file
        print (requestedNames)
        finalFromCommandLine = _parse_varnames(fileCommonNames, requestedNames,
                                               defaultValues['epsilon'], defaultValues['missing_value'])
        for name, epsilon, missing in finalFromCommandLine :
            ## we'll use the variable's name as the display name for the time being
            finalNames[name] = {}
            # make sure we pick up any other controlling defaults
            finalNames[name].update(defaultValues) 
            # but override the values that would have been determined by _parse_varnames
            finalNames[name]['variable_name'] = name
            finalNames[name]['epsilon'] = epsilon
            
            # load the missing value if it was not provided
            missing, missing_b = _get_missing_values_if_needed((fileAObject, fileBObject), name,
                                                               missing_value_A=missing, missing_value_B=missing)
            finalNames[name]['missing_value'] = missing 
            finalNames[name]['missing_value_alt_in_b'] = missing_b
    
    LOG.debug("Final selected set of variables to analyze:")
    LOG.debug(str(finalNames))
    
    return finalNames, nameComparison

def _get_missing_values_if_needed((fileA, fileB),
                                  var_name, alt_var_name=None, 
                                  missing_value_A=None, missing_value_B=None) :
    """
    get the missing values for two files based on the variable name(s)
    if the alternate variable name is passed it will be used for the
    second file in place of the primary variable name
    """
    # if we don't have an alternate variable name, use the existing one
    if alt_var_name is None :
        alt_var_name = var_name
    
    if missing_value_A is None :
        missing_value_A = fileA.missing_value(var_name)
    
    if missing_value_B is None :
        missing_value_B = fileB.missing_value(alt_var_name)
    
    return missing_value_A, missing_value_B

def _load_config_or_options(aPath, bPath, optionsSet, requestedVars = [ ]) :
    """
    load information on how the user wants to run the command from a dictionary of options 
    and info on the files and variables to compare
    note: the options may include a configuration file, which will override many of the
    settings in the options
    """
    
    # basic defaults for stuff we will need to return
    runInfo = {}
    runInfo.update(glance_setting_defaults) # get the default settings
    if ('noLonLatVars' not in optionsSet) or (not optionsSet['noLonLatVars']):
        runInfo.update(glance_lon_lat_defaults) # get the default lon/lat info
    
    # by default, we don't have any particular variables to analyze
    desiredVariables = { }
    # use the built in default values, to start with
    defaultsToUse = glance_analysis_defaults.copy()
    
    requestedNames = None
    
    # set up the paths, they can only come from the command line
    paths = {}
    paths['a'] = aPath 
    paths['b'] = bPath
    paths['out'] = optionsSet['outputpath']
    
    # check to see if the user wants to use a config file and if the path exists
    requestedConfigFile = optionsSet['configFile']
    usedConfigFile = False
    if (not (requestedConfigFile is None)) and os.path.exists(requestedConfigFile):
        
        LOG.info ("Using Config File Settings")
        
        # this will handle relative paths
        requestedConfigFile = os.path.abspath(os.path.expanduser(requestedConfigFile))
        
        # split out the file base name and the file path
        (filePath, fileName) = os.path.split(requestedConfigFile)
        splitFileName = fileName.split('.')
        fileBaseName = fileName[:-3] # remove the '.py' from the end
        
        # hang onto info about the config file for later
        runInfo['config_file_name'] = fileName
        runInfo['config_file_path'] = requestedConfigFile
        
        # load the file
        LOG.debug ('loading config file: ' + str(requestedConfigFile))
        glanceRunConfig = imp.load_module(fileBaseName, file(requestedConfigFile, 'U'),
                                          filePath, ('.py' , 'U', 1))
        
        # this is an exception, since it is not advertised to the user we don't expect it to be in the file
        # (at least not at the moment, it could be added later and if they did happen to put it in the
        # config file, it would override this line)
        runInfo['shouldIncludeReport'] = not optionsSet['imagesOnly']
        runInfo['noLonLatVars'] = optionsSet['noLonLatVars']
        
        # get everything from the config file
        runInfo.update(glanceRunConfig.settings)
        if ('noLonLatVars' not in runInfo) or (not runInfo['noLonLatVars']) :
            runInfo.update(glanceRunConfig.lat_lon_info) # get info on the lat/lon variables
        
        # get any requested names
        requestedNames = glanceRunConfig.setOfVariables.copy()
        # user selected defaults, if they omit any we'll still be using the program defaults
        defaultsToUse.update(glanceRunConfig.defaultValues)
        
        usedConfigFile = True
        
    # if we didn't get the info from the config file for some reason
    # (the user didn't want to, we couldn't, etc...) get it from the command line options
    if not usedConfigFile:
        
        LOG.info ('Using Command Line Settings')
        
        # so get everything from the options directly
        runInfo['shouldIncludeReport'] = not optionsSet['imagesOnly']
        runInfo['shouldIncludeImages'] = not optionsSet['htmlOnly']
        runInfo['doFork'] = optionsSet['doFork']
        
        # only record these if we are using lon/lat
        runInfo['noLonLatVars']       = optionsSet['noLonLatVars']
        if not runInfo['noLonLatVars'] :
            runInfo['latitude']        = optionsSet['latitudeVar']  or runInfo['latitude']
            runInfo['longitude']       = optionsSet['longitudeVar'] or runInfo['longitude']
            runInfo['lon_lat_epsilon'] = optionsSet['lonlatepsilon']
        
        # get any requested names from the command line
        requestedNames = requestedVars or ['.*'] 
        
        # user selected defaults
        defaultsToUse['epsilon'] = optionsSet['epsilon']
        defaultsToUse['missing_value'] = optionsSet['missing']
        
        # note: there is no way to set the tolerances from the command line
    
    return paths, runInfo, defaultsToUse, requestedNames, usedConfigFile

def _get_and_analyze_lon_lat (fileObject,
                              latitudeVariableName, longitudeVariableName,
                              latitudeDataFilterFn=None, longitudeDataFilterFn=None) :
    """
    get the longitude and latitude data from the given file, assuming they are in the given variable names
    and analyze them to identify spacially invalid data (ie. data that would fall off the earth)
    """
    # get the data from the file TODO, handle these exits out in the calling method?
    LOG.info ('longitude name: ' + longitudeVariableName)
    try :
        longitudeData = array(fileObject[longitudeVariableName], dtype=float)
    except CDFError :
        LOG.warn ('Unable to retrieve longitude data. The variable name (' + longitudeVariableName +
                  ') may not exist in this file or an error may have occured while attempting to' +
                  ' access the data.')
        LOG.warn ('Unable to continue analysis without longitude data. Aborting analysis.')
        sys.exit(1)
    LOG.info ('latitude name: '  + latitudeVariableName)
    try :
        latitudeData  = array(fileObject[latitudeVariableName],  dtype=float)
    except CDFError :
        LOG.warn ('Unable to retrieve latitude data. The variable name (' + latitudeVariableName +
                  ') may not exist in this file or an error may have occured while attempting to' +
                  ' access the data.')
        LOG.warn ('Unable to continue analysis without latitude data. Aborting analysis.')
        sys.exit(1)
    
    # if we have filters, use them
    if not (latitudeDataFilterFn is None) :
        latitudeData = latitudeDataFilterFn(latitudeData)
        LOG.debug ('latitude size after application of filter: '  + str(latitudeData.shape))
    if not (longitudeDataFilterFn is None) :
        longitudeData = longitudeDataFilterFn(longitudeData)
        LOG.debug ('longitude size after application of filter: ' + str(longitudeData.shape))
    
    # build a mask of our spacially invalid data TODO, load actual valid range attributes?
    invalidLatitude = (latitudeData < -90) | (latitudeData > 90) | ~isfinite(latitudeData)
    invalidLongitude = (longitudeData < -180)   | (longitudeData > 360) | ~isfinite(longitudeData)
    spaciallyInvalidMask = invalidLatitude | invalidLongitude
    
    # analyze our spacially invalid data
    percentageOfSpaciallyInvalidPts, numberOfSpaciallyInvalidPts = _get_percentage_from_mask(spaciallyInvalidMask)
    
    return longitudeData, latitudeData, spaciallyInvalidMask, {
                                                               'totNumInvPts': numberOfSpaciallyInvalidPts,
                                                               'perInvPts':    percentageOfSpaciallyInvalidPts
                                                               }

def _get_percentage_from_mask(dataMask) :
    """
    given a mask that marks the elements we want the percentage of as True (and is the size of our original data),
    figure out what percentage of the whole they are
    """
    numMarkedDataPts = sum(dataMask)
    totalDataPts = dataMask.size
    # avoid dividing by 0
    if totalDataPts is 0 :
        return 0.0, 0
    percentage = 100.0 * float(numMarkedDataPts) / float(totalDataPts)
    
    return percentage, numMarkedDataPts

def _check_lon_lat_equality(longitudeA, latitudeA,
                            longitudeB, latitudeB,
                            ignoreMaskA, ignoreMaskB,
                            llepsilon, doMakeImages, outputPath) :
    """
    check to make sure the longitude and latitude are equal everywhere that's not in the ignore masks
    if they are not and doMakeImages was passed as True, generate appropriate figures to show where
    return the number of points where they are not equal (0 would mean they're the same)
    """
    # first of all, if the latitude and longitude are not the same shape, then things can't ever be "equal"
    if (longitudeA.shape != longitudeB.shape) | (latitudeA.shape != latitudeB.shape) :
        return None
    
    lon_lat_not_equal_points_count = 0
    lon_lat_not_equal_points_percent = 0.0
    
    # get information about how the latitude and longitude differ
    longitudeDiff, finiteLongitudeMask, _, _, lon_not_equal_mask, _, _, _ = delta.diff(longitudeA, longitudeB,
                                                                                       llepsilon,
                                                                                       (None, None),
                                                                                       (ignoreMaskA, ignoreMaskB))
    latitudeDiff,  finiteLatitudeMask,  _, _, lat_not_equal_mask, _, _, _ = delta.diff(latitudeA,  latitudeB,
                                                                                       llepsilon,
                                                                                       (None, None),
                                                                                       (ignoreMaskA, ignoreMaskB))
    
    lon_lat_not_equal_mask = lon_not_equal_mask | lat_not_equal_mask
    lon_lat_not_equal_points_count = sum(lon_lat_not_equal_mask)
    lon_lat_not_equal_points_percent = (float(lon_lat_not_equal_points_count) / float(lon_lat_not_equal_mask.size)) * 100.0
    
    # if we have unequal points, create user legible info about the problem
    if (lon_lat_not_equal_points_count > 0) :
        LOG.warn("Possible mismatch in values stored in file a and file b longitude and latitude values."
                 + " Depending on the degree of mismatch, some data value comparisons may be "
                 + "distorted or spacially nonsensical.")
        # if we are making images, make two showing the invalid lons/lats
        if (doMakeImages) :
            
            if (len(longitudeA[~ignoreMaskA]) > 0) and (len(latitudeA[~ignoreMaskA]) > 0) :
                plot.plot_and_save_spacial_trouble(longitudeA, latitudeA,
                                                   lon_lat_not_equal_mask,
                                                   ignoreMaskA,
                                                   "A", "Lon./Lat. Points Mismatched between A and B\n" +
                                                   "(Shown in A)",
                                                   "LonLatMismatch",
                                                   outputPath, True)
            
            if (len(longitudeB[~ignoreMaskB]) > 0) and (len(latitudeB[~ignoreMaskB]) > 0) :
                plot.plot_and_save_spacial_trouble(longitudeB, latitudeB,
                                                   lon_lat_not_equal_mask,
                                                   ignoreMaskB,
                                                   "B", "Lon./Lat. Points Mismatched between A and B\n" +
                                                   "(Shown in B)",
                                                   "LonLatMismatch",
                                                   outputPath, True)
    
    # setup our return data
    returnInfo = {}
    returnInfo['lon_lat_not_equal_points_count'] = lon_lat_not_equal_points_count
    returnInfo['lon_lat_not_equal_points_percent'] = lon_lat_not_equal_points_percent
    
    return returnInfo

def _compare_spatial_invalidity(invalid_in_a_mask, invalid_in_b_mask, spatial_info,
                                longitude_a, longitude_b, latitude_a, latitude_b,
                                do_include_images, output_path) :
    """
    Given information about where the two files are spatially invalid, figure
    out what invalidity they share and save information or plots for later use
    also build a shared longitude/latitude based on A but also including valid
    points in B
    """
    
    # for convenience,
    # make a combined mask
    invalid_in_common_mask = invalid_in_a_mask | invalid_in_b_mask
    # make a "common" latitude based on A
    longitude_common = longitude_a
    latitude_common = latitude_a
    
    # compare our spacialy invalid info
    spatial_info['perInvPtsInBoth'] = spatial_info['file A']['perInvPts']
            # a default that will hold if the two files have the same spatially invalid pts
    if not all(invalid_in_a_mask.ravel() == invalid_in_b_mask.ravel()) : 
        LOG.info("Mismatch in number of spatially invalid points. " +
                 "Files may not have corresponding data where expected.")
        
        # figure out which points are only valid in one of the two files
        valid_only_in_mask_a = (~invalid_in_a_mask) & invalid_in_b_mask
        spatial_info['file A']['numInvPts'] = sum(valid_only_in_mask_a.ravel())
        valid_only_in_mask_b = (~invalid_in_b_mask) & invalid_in_a_mask
        spatial_info['file B']['numInvPts'] = sum(valid_only_in_mask_b.ravel())
        
        # so how many do they have together?
        spatial_info['perInvPtsInBoth'] = _get_percentage_from_mask(invalid_in_common_mask)[0]
        # make a "clean" version of the lon/lat
        longitude_common[valid_only_in_mask_a] = longitude_a[valid_only_in_mask_a]
        longitude_common[valid_only_in_mask_b] = longitude_b[valid_only_in_mask_b]
        latitude_common [valid_only_in_mask_a] = latitude_a [valid_only_in_mask_a]
        latitude_common [valid_only_in_mask_b] = latitude_b [valid_only_in_mask_b]
        
        # plot the points that are only valid one file and not the other
        if ((spatial_info['file A']['numInvPts'] > 0) and (do_include_images) and
            (len(longitude_a[~invalid_in_a_mask]) > 0) and (len(latitude_a[~invalid_in_a_mask]) > 0)) :
            plot.plot_and_save_spacial_trouble(longitude_a, latitude_a,
                                               valid_only_in_mask_a,
                                               invalid_in_a_mask,
                                               "A", "Points only valid in\nFile A\'s longitude & latitude",
                                               "SpatialMismatch",
                                               output_path, True)
        if ((spatial_info['file B']['numInvPts'] > 0) and (do_include_images) and
            (len(longitude_b[~invalid_in_b_mask]) > 0) and (len(latitude_b[~invalid_in_b_mask]) > 0)
            ) :
            plot.plot_and_save_spacial_trouble(longitude_b, latitude_b,
                                               valid_only_in_mask_b,
                                               invalid_in_b_mask,
                                               "B", "Points only valid in\nFile B\'s longitude & latitude",
                                               "SpatialMismatch",
                                               output_path, True)
    
    return invalid_in_common_mask, spatial_info, longitude_common, latitude_common

def _handle_lon_lat_info (lon_lat_settings, a_file_object, b_file_object, output_path, should_make_images=False) :
    """
    Manage loading and comparing longitude and latitude information for two files
    
    Note: if the error message is returned as anything but None, something uncrecoverable
    occured while trying to get the lon/lat info. TODO, replace this with a proper thrown exception
    """
    # a place to save some general stats about our lon/lat data
    spatialInfo = { }
    # a place to put possible error messages TODO remove this in favor of an exception
    error_msg = None
    
    # if there is no lon/lat specified, stop now
    if ('longitude' not in lon_lat_settings) or ('latitude' not in lon_lat_settings) :
        return { }, spatialInfo, error_msg
    
    # if we should not be comparing against the logitude and latitude, stop now
    print ('lon_lat_settings: ' + str(lon_lat_settings))
    
    # figure out the names to be used for the longitude and latitude variables
    a_longitude_name = lon_lat_settings['longitude']
    a_latitude_name =  lon_lat_settings['latitude']
    b_longitude_name = a_longitude_name
    b_latitude_name =  a_latitude_name
    
    # if we have alternate b names, use those for b instead
    if ('longitude_alt_name_in_b' in lon_lat_settings) :
        b_longitude_name = lon_lat_settings['longitude_alt_name_in_b']
    if ( 'latitude_alt_name_in_b' in lon_lat_settings):
        b_latitude_name  = lon_lat_settings['latitude_alt_name_in_b']
        
    # if we need to load our lon/lat from different files, open those files
    
    # for the a file, do we have an alternate?
    file_for_a_lon_lat = a_file_object
    if ('a_lon_lat_from_alt_file' in lon_lat_settings) :
        LOG.info("Loading alternate file (" + lon_lat_settings['a_lon_lat_from_alt_file'] + ") for file a longitude/latitude.")
        file_for_a_lon_lat, _ = _setup_file(lon_lat_settings['a_lon_lat_from_alt_file'], "\t")
    
    # for the b file, do we have an alternate?
    file_for_b_lon_lat = b_file_object
    if ('b_lon_lat_from_alt_file' in lon_lat_settings) :
        LOG.info("Loading alternate file (" + lon_lat_settings['b_lon_lat_from_alt_file'] + ") for file b longitude/latitude.")
        file_for_b_lon_lat, _ = _setup_file(lon_lat_settings['b_lon_lat_from_alt_file'], "\t")
    
    # load our longitude and latitude and do some analysis on them
    longitude_a, latitude_a, spaciallyInvalidMaskA, spatialInfo['file A'] = \
        _get_and_analyze_lon_lat (file_for_a_lon_lat, a_latitude_name, a_longitude_name, 
                                  lon_lat_settings['data_filter_function_lat_in_a'], lon_lat_settings['data_filter_function_lon_in_a'])
    longitude_b, latitude_b, spaciallyInvalidMaskB, spatialInfo['file B'] = \
        _get_and_analyze_lon_lat (file_for_b_lon_lat, b_latitude_name, b_longitude_name,
                                  lon_lat_settings['data_filter_function_lat_in_b'], lon_lat_settings['data_filter_function_lon_in_b'])
    
    # test the "valid" values in our lon/lat
    moreSpatialInfo = _check_lon_lat_equality(longitude_a, latitude_a, longitude_b, latitude_b,
                                              spaciallyInvalidMaskA, spaciallyInvalidMaskB,
                                              lon_lat_settings['lon_lat_epsilon'],
                                              should_make_images, output_path)
    # if we got the worst type of error result from the comparison this data is too dissimilar to continue
    if moreSpatialInfo is None :
        error_msg = ("Unable to reconcile sizes of longitude and latitude for variables "
                 + str(lon_lat_settings['longitude']) + str(longitude_a.shape) + "/"
                 + str(lon_lat_settings['latitude'])  + str(latitude_a.shape) + " in file A and variables "
                 + str(b_longitude_name) + str(longitude_b.shape) + "/"
                 + str(b_latitude_name)  + str(latitude_b.shape) + " in file B. Aborting attempt to compare files.")
        return { }, { }, error_msg # things have gone wrong
    # update our existing spatial information
    spatialInfo.update(moreSpatialInfo)
    
    # compare our spatially invalid info to see if the two files have invalid longitudes and latitudes in the same places
    spaciallyInvalidMask, spatialInfo, longitude_common, latitude_common = \
                            _compare_spatial_invalidity(spaciallyInvalidMaskA, spaciallyInvalidMaskB, spatialInfo,
                                                        longitude_a, longitude_b, latitude_a, latitude_b,
                                                        should_make_images, output_path)
    
    return {'a':      {"lon": longitude_a,      "lat": latitude_a,      "inv_mask": spaciallyInvalidMaskA},
            'b':      {"lon": longitude_b,      "lat": latitude_b,      "inv_mask": spaciallyInvalidMaskB},
            'common': {"lon": longitude_common, "lat": latitude_common, "inv_mask": spaciallyInvalidMask}   }, \
           spatialInfo, error_msg

def _open_and_process_files (args, numFilesExpected):
    """
    open files listed in the args and get information about the variables in them
    """
    # get all the file names
    fileNames = args[:numFilesExpected]
    # open all the files & get their variable names
    files = {}
    commonNames = None
    for fileName in fileNames:
        LOG.info("opening %s" % fileName)
        files[fileName] = {}
        tempFileObject = (io.open(fileName))
        files[fileName]['fileObject'] = tempFileObject
        tempNames = set(tempFileObject())
        LOG.debug ('variable names for ' + fileName + ': ' + str(tempNames)) 
        files[fileName]['varNames'] = tempNames
        if commonNames is None :
            commonNames = tempNames
        else :
            commonNames = commonNames.intersection(tempNames)
    files['commonVarNames'] = commonNames
    
    return files

def _check_pass_or_fail(varRunInfo, variableStats, defaultValues) :
    """
    Check whether the variable passed analysis, failed analysis, or
    did not need to be quantitatively tested
    
    also returns information about the fractions of failure
    """
    didPass = None
    
    # get our tolerance values
    
    # get the tolerance for failures in comparison compared to epsilon
    epsilonTolerance = None
    if ('epsilon_failure_tolerance' in varRunInfo) :
        epsilonTolerance = varRunInfo['epsilon_failure_tolerance']
    else :
        epsilonTolerance = defaultValues['epsilon_failure_tolerance']
    # get the tolerance for failures in amount of nonfinite data
    # found in spatially valid areas
    nonfiniteTolerance = None
    if ('nonfinite_data_tolerance'  in varRunInfo) :
        nonfiniteTolerance = varRunInfo['nonfinite_data_tolerance']
    else :
        nonfiniteTolerance = defaultValues['nonfinite_data_tolerance']
    
    # test to see if we passed or failed
    
    # check for our epsilon tolerance
    failed_fraction = 0.0
    if not (epsilonTolerance is None) :
        failed_fraction = variableStats['Numerical Comparison Statistics']['diff_outside_epsilon_fraction']
        didPass = failed_fraction <= epsilonTolerance
    
    # check to see if it failed on nonfinite data
    non_finite_diff_fraction = 0.0
    if not (nonfiniteTolerance is None) :
        non_finite_diff_fraction = variableStats['Finite Data Statistics']['finite_in_only_one_fraction']
        passedNonFinite = non_finite_diff_fraction <= nonfiniteTolerance
        
        # combine the two test results
        if (didPass is None) :
            didPass = passedNonFinite
        else :
            didPass = didPass and passedNonFinite
    
    return didPass, failed_fraction, non_finite_diff_fraction

def _get_run_identification_info( ) :
    """
    get info about what user/machine/version of glance is being used
    """
    info_to_return = { }
    
    # get info on who's doing the run and where
    info_to_return['machine'] = os.uname()[1]      # the name of the machine running the report
    info_to_return['user'] = os.getenv("LOGNAME")  #os.getlogin() # the name of the user running the report
    info_to_return['version'] = _get_glance_version_string()
    
    return info_to_return

def _get_glance_version_string() :
    version_num = pkg_resources.require('glance')[0].version
    
    return "glance, version " + str(version_num) 

def _get_name_info_for_variable(original_display_name, variable_run_info) :
    """
    based on the variable run info, figure out the various names for
    the variable and return them
    
    the various names are:
    
    technical_name -            the name the variable is listed under in the file
    b_variable_technical_name - the name the variable is listed under in the b file (may be the same as technical_name)
    explanation_name -          the more verbose name that will be shown to the user to identify the variable
    original_display_name -     the display name given by the user to describe the variable
    """
    
    # figure out the various name related info
    technical_name = variable_run_info['variable_name']
    explanation_name = technical_name # for now, will add to this later
    
    # if B has an alternate variable name, figure that out
    b_variable_technical_name = technical_name
    if 'alternate_name_in_B' in variable_run_info :
        b_variable_technical_name = variable_run_info['alternate_name_in_B']
        # put both names in our explanation
        explanation_name = explanation_name + " / " + b_variable_technical_name
    
    # show both the display and current explanation names if they differ
    if not (original_display_name == explanation_name) :
        explanation_name = original_display_name + ' (' + explanation_name + ')'
    
    return technical_name, b_variable_technical_name, explanation_name

def reportGen_library_call (a_path, b_path, var_list=[ ],
                            options_set={ },
                            # todo, this doesn't yet do anything
                            do_document=False,
                            # todo, the output channel does nothing at the moment
                            output_channel=sys.stdout) :
    """
    this method handles the actual work of the reportGen command line tool
    and can also be used as a library routine, pass in the slightly parsed
    command line input, or call it as a library function... be sure to fill
    out the options
    TODO at the moment the options are very brittle and need to be fully filled
    or this method will fail badly (note: the addition of some glance defaults
    has minimized the problem, but you still need to be careful when dealing with
    optional boolean values. this needs more work.)
    """
    
    # load the user settings from either the command line or a user defined config file
    pathsTemp, runInfo, defaultValues, requestedNames, usedConfigFile = _load_config_or_options(a_path, b_path,
                                                                                                options_set,
                                                                                                requestedVars = var_list)
    
    # note some of this information for debugging purposes
    LOG.debug('paths: ' +           str(pathsTemp))
    LOG.debug('defaults: ' +        str(defaultValues))
    LOG.debug('run information: ' + str(runInfo))
    
    # if we wouldn't generate anything, just stop now
    if (not runInfo['shouldIncludeImages']) and (not runInfo['shouldIncludeReport']) :
        LOG.warn("User selection of no image generation and no report generation will result in no " +
                 "content being generated. Aborting generation function.")
        return
    
    # hang onto info to identify who/what/when/where/etc. the report is being run by/for 
    runInfo.update(_get_run_identification_info( ))
    
    # deal with the input and output files
    if not (os.path.isdir(pathsTemp['out'])) :
        LOG.info("Specified output directory (" + pathsTemp['out'] + ") does not exist.")
        LOG.info("Creating output directory.")
        os.makedirs(pathsTemp['out'])
    # open the files
    files = {}
    LOG.info("Processing File A:")
    aFile, files['file A'] = _setup_file(pathsTemp['a'], "\t")
    if aFile is None:
        LOG.warn("Unable to continue with comparison because file a (" + pathsTemp['a'] + ") could not be opened.")
        sys.exit(1)
    LOG.info("Processing File B:")
    bFile, files['file B'] = _setup_file(pathsTemp['b'], "\t")
    if bFile is None:
        LOG.warn("Unable to continue with comparison because file b (" + pathsTemp['b'] + ") could not be opened.")
        sys.exit(1)
    
    # get information about the names the user requested
    finalNames, nameStats = _resolve_names(aFile, bFile,
                                           defaultValues,
                                           requestedNames, usedConfigFile)
    
    # if there is longitude and latitude info, handle the longitude and latitude
    #if 'lon_lat' in runInfo : TODO, how can we handle cases where lon/lat is meaningless?
    
    print("output dir: " + str(pathsTemp['out']))
    
    # return for lon_lat_data variables will be in the form 
    #{"lon": longitude_data,      "lat": latitude_data,      "inv_mask": spaciallyInvalidMaskData}
    # or { } if there is no lon/lat info
    lon_lat_data, spatialInfo, fatalErrorMsg = _handle_lon_lat_info (runInfo, 
                                                                     aFile, bFile,
                                                                     pathsTemp['out'],
                                                                     should_make_images = runInfo["shouldIncludeImages"])
    if fatalErrorMsg is not None :
        LOG.warn(fatalErrorMsg)
        sys.exit(1)
    
    # if there is an approved lon/lat shape, hang on to that for future checks
    good_shape_from_lon_lat = None
    if len(lon_lat_data.keys()) > 0:
        good_shape_from_lon_lat = lon_lat_data['common']['lon'].shape
    
    # this will hold information for the summary report
    # it will be in the form
    # [displayName] = {"passEpsilonPercent":     percent ok with epsilon,
    #                  "finite_similar_percent": percent with the same finiteness, 
    #                  "epsilon":                epsilon value used}
    variableComparisons = {}
    
    # go through each of the possible variables in our files
    # and make a report section with images for whichever ones we can
    for displayName in finalNames:
        
        # pull out the information for this variable analysis run
        varRunInfo = finalNames[displayName].copy()
        
        # get the various names
        technical_name, b_variable_technical_name, \
                explanationName = _get_name_info_for_variable(displayName, varRunInfo)
        
        print('analyzing: ' + explanationName + ')')
        
        # get the data for the variable 
        aData = aFile[technical_name]
        bData = bFile[b_variable_technical_name]
        
        # apply data filter functions if needed
        if ('data_filter_function_a' in varRunInfo) :
            aData = varRunInfo['data_filter_function_a'](aData)
            LOG.debug ("filter function was applied to file A data for variable: " + explanationName)
        if ('data_filter_function_b' in varRunInfo) :
            bData = varRunInfo['data_filter_function_b'](bData)
            LOG.debug ("filter function was applied to file B data for variable: " + explanationName)
        
        # pre-check if this data should be plotted and if it should be compared to the longitude and latitude
        include_images_for_this_variable = ((not('shouldIncludeImages' in runInfo)) or (runInfo['shouldIncludeImages']))
        if 'shouldIncludeImages' in varRunInfo :
            include_images_for_this_variable = varRunInfo['shouldIncludeImages']
        do_not_test_with_lon_lat = (not include_images_for_this_variable) or (len(lon_lat_data.keys()) <= 0)
        
        LOG.debug ("do_not_test_with_lon_lat = " + str(do_not_test_with_lon_lat))
        LOG.debug ("include_images_for_this_variable = " + str(include_images_for_this_variable))
        
        # handle vector data
        isVectorData = False # TODO actually figure out if we have vector data from user inputted settings
        
        # TODO This if is for testing data colocation, this feature is not yet functional
        if False :
            (aData, bData, newLongitude, newLatitude), \
            (aUnmatchedData,             unmatchedALongitude, unmatchedALatitude), \
            (bUnmatchedData,             unmatchedBLongitude, unmatchedBLatitude) = \
                    delta.colocate_matching_points_within_epsilon((aData, lon_lat_data['a']['lon'], lon_lat_data['a']['lat']),
                                                                  (bData, lon_lat_data['b']['lon'], lon_lat_data['b']['lat']),
                                                                  0.03,
                                                                  invalidAMask=lon_lat_data['a']['inv_mask'],
                                                                  invalidBMask=lon_lat_data['b']['inv_mask'])
            lon_lat_data['a'] = {
                                 'lon': newLongitude,
                                 'lat': newLatitude,
                                 'inv_mask': zeros(aData.shape, dtype=bool)
                                 }
            lon_lat_data['b'] = {
                                 'lon': newLongitude,
                                 'lat': newLatitude,
                                 'inv_mask': zeros(aData.shape, dtype=bool)
                                 }
            lon_lat_data['common'] = {
                                 'lon': newLongitude,
                                 'lat': newLatitude,
                                 'inv_mask': zeros(aData.shape, dtype=bool)
                                 }
            good_shape_from_lon_lat = newLatitude.shape
        
        # check if this data can be displayed but
        # don't compare lon/lat sizes if we won't be plotting
        if ( (aData.shape == bData.shape) 
             and 
             ( do_not_test_with_lon_lat
              or
              ((aData.shape == good_shape_from_lon_lat) and (bData.shape == good_shape_from_lon_lat)) ) ) :
            
            # check to see if there is a directory to put information about this variable in,
            # if not then create it
            variableDir = os.path.join(pathsTemp['out'], './' + displayName)
            varRunInfo['variable_dir'] = variableDir
            varRunInfo['variable_report_path_escaped'] = quote(os.path.join(displayName, 'index.html'))
            LOG.debug ("Directory selected for variable information: " + varRunInfo['variable_report_path_escaped'])
            if not (os.path.isdir(variableDir)) :
                LOG.debug("Variable directory (" + variableDir + ") does not exist.")
                LOG.debug("Creating variable directory.")
                os.makedirs(variableDir)
            
            # figure out the masks we want, and then do our statistical analysis
            mask_a_to_use = None
            mask_b_to_use = None
            if not do_not_test_with_lon_lat :
                mask_a_to_use = lon_lat_data['a']['inv_mask']
                mask_b_to_use = lon_lat_data['b']['inv_mask']
            variable_stats = delta.summarize(aData, bData,
                                             varRunInfo['epsilon'],
                                             (varRunInfo['missing_value'],
                                             varRunInfo['missing_value_alt_in_b']),
                                             mask_a_to_use, mask_b_to_use)
            
            # add a little additional info to our variable run info before we squirrel it away
            varRunInfo['time'] = datetime.datetime.ctime(datetime.datetime.now())  # todo is this needed?
            didPass, epsilon_failed_fraction, non_finite_fail_fraction = _check_pass_or_fail(varRunInfo,
                                                                                     variable_stats,
                                                                                     defaultValues)
            varRunInfo['did_pass'] = didPass
            
            # based on the settings and whether the variable passsed or failed,
            # should we include images for this variable?
            if ('only_plot_on_fail' in varRunInfo) and varRunInfo['only_plot_on_fail'] :
                include_images_for_this_variable = include_images_for_this_variable and (not didPass)
                varRunInfo['shouldIncludeImages'] = include_images_for_this_variable
            
            # to hold the names of any images created
            image_names = {
                            'original': [ ],
                            'compared': [ ]
                            }
            
            # create the images for this variable
            # TODO, will need to handle averaged/sliced 3D data at some point
            if (include_images_for_this_variable) :
                
                plotFunctionGenerationObjects = [ ]
                
                # if the data is the same size, we can always make our basic statistical comparison plots
                if (aData.shape == bData.shape) :
                    plotFunctionGenerationObjects.append(plotcreate.BasicComparisonPlotsFunctionFactory())
                
                # if it's vector data with longitude and latitude, quiver plot it on the Earth
                if isVectorData and (not do_not_test_with_lon_lat) :
                    plotFunctionGenerationObjects.append(plotcreate.MappedQuiverPlotFunctionFactory())
                
                # if the data is one dimensional we can plot it as lines
                elif   (len(aData.shape) is 1) :
                    plotFunctionGenerationObjects.append(plotcreate.LinePlotsFunctionFactory())
                
                # if the data is 2D we have some options based on the type of data
                elif (len(aData.shape) is 2) :
                    
                    # if the data is not mapped to a longitude and latitude, just show it as an image
                    if (do_not_test_with_lon_lat) :
                        plotFunctionGenerationObjects.append(plotcreate.IMShowPlotFunctionFactory())
                    
                    # if it's 2D and mapped to the Earth, contour plot it on the earth
                    else :
                        plotFunctionGenerationObjects.append(plotcreate.MappedContourPlotFunctionFactory())
                
                # plot our lon/lat related info
                image_names['original'], image_names['compared'] = \
                    plot.plot_and_save_comparison_figures \
                            (aData, bData,
                             plotFunctionGenerationObjects,
                             varRunInfo['variable_dir'],
                             displayName,
                             varRunInfo['epsilon'],
                             varRunInfo['missing_value'],
                             missingValueAltInB = varRunInfo['missingValueAltInB'] if 'missingValueAltInB' in varRunInfo else None,
                             lonLatDataDict=lon_lat_data,
                             dataRanges     = varRunInfo['display_ranges']      if 'display_ranges'      in varRunInfo else None,
                             dataRangeNames = varRunInfo['display_range_names'] if 'display_range_names' in varRunInfo else None,
                             dataColors     = varRunInfo['display_colors']      if 'display_colors'      in varRunInfo else None,
                             makeSmall=True,
                             doFork=runInfo['doFork'],
                             shouldClearMemoryWithThreads=runInfo['useThreadsToControlMemory'],
                             shouldUseSharedRangeForOriginal=runInfo['useSharedRangeForOriginal'],
                             doPlotSettingsDict = varRunInfo)
                
                print("\tfinished creating figures for: " + explanationName)
            
            # create the report page for this variable
            if (runInfo['shouldIncludeReport']) :
                
                # hang on to our good % and other info to describe our comparison
                epsilonPassedPercent = (1.0 -  epsilon_failed_fraction) * 100.0
                finitePassedPercent  = (1.0 - non_finite_fail_fraction) * 100.0 
                variableComparisons[displayName] = {'pass_epsilon_percent':   epsilonPassedPercent,
                                                    'finite_similar_percent': finitePassedPercent,
                                                    'variable_run_info':      varRunInfo
                                                    }
                
                print ('\tgenerating report for: ' + explanationName) 
                report.generate_and_save_variable_report(files,
                                                         varRunInfo, runInfo,
                                                         variable_stats,
                                                         spatialInfo,
                                                         image_names,
                                                         varRunInfo['variable_dir'], "index.html")
        
        # if we can't compare the variable, we should tell the user 
        else :
            message = (explanationName + ' ' + 
                     'could not be compared. This may be because the data for this variable does not match in shape ' +
                     'between the two files (file A data shape: ' + str(aData.shape) + '; file B data shape: '
                     + str(bData.shape) + ')')
            if do_not_test_with_lon_lat :
                message = message + '.'
            else :
                message = (message + ' or the data may not match the shape of the selected longitude ' +
                     str(good_shape_from_lon_lat) + ' and ' + 'latitude ' + str(good_shape_from_lon_lat) + ' variables.')
            LOG.warn(message)
        
    # the end of the loop to examine all the variables
    
    # generate our general report pages once we've analyzed all the variables
    if (runInfo['shouldIncludeReport']) :
        
        # get the current time
        runInfo['time'] = datetime.datetime.ctime(datetime.datetime.now())
        
        # make the main summary report
        print ('generating summary report')
        report.generate_and_save_summary_report(files,
                                                pathsTemp['out'], 'index.html',
                                                runInfo,
                                                variableComparisons, 
                                                spatialInfo,
                                                nameStats)
        
        # make the glossary
        print ('generating glossary')
        report.generate_and_save_doc_page(delta.STATISTICS_DOC, pathsTemp['out'])
    
    return

def stats_library_call(afn, bfn, var_list=[ ],
                       options_set={ },
                       do_document=False,
                       output_channel=sys.stdout): 
    """
    this method handles the actual work of the stats command line tool and
    can also be used as a library routine, simply pass in an output channel
    and/or use the returned dictionary of statistics for your own form of
    display.
    TODO, should this move to a different file?
    """
    # unpack some options
    epsilon_val = options_set['epsilon']
    missing_val = options_set['missing']
    
    LOG.debug ("file a: " + afn)
    LOG.debug ("file b: " + bfn)
    
    # open the files
    filesInfo = _open_and_process_files([afn, bfn], 2)
    aFile = filesInfo[afn]['fileObject']
    bFile = filesInfo[bfn]['fileObject']
    
    # figure out the variable names and their individual settings
    if len(var_list) <= 0 :
        var_list = ['.*']
    names = _parse_varnames( filesInfo['commonVarNames'], var_list, epsilon_val, missing_val )
    LOG.debug(str(names))
    doc_each  = do_document and len(names)==1
    doc_atend = do_document and len(names)!=1
    
    for name,epsilon,missing in names:
        aData = aFile[name]
        bData = bFile[name]
        if missing is None:
            amiss = aFile.missing_value(name)
            bmiss = bFile.missing_value(name)
        else:
            amiss,bmiss = missing,missing
        LOG.debug('comparing %s with epsilon %s and missing %s,%s' % (name,epsilon,amiss,bmiss))
        aval = aData
        bval = bData
        print >> output_channel, '-'*32
        print >> output_channel, name
        print >> output_channel, '' 
        lal = list(delta.summarize(aval,bval,epsilon,(amiss,bmiss)).items()) 
        lal.sort()
        for dictionary_title, dict_data in lal:
            print >> output_channel, '%s' %  dictionary_title
            dict_data
            for each_stat in sorted(list(dict_data)):
                print >> output_channel, '  %s: %s' % (each_stat, dict_data[each_stat])
                if doc_each: print >> output_channel, ('    ' + delta.STATISTICS_DOC[each_stat])
            print >> output_channel, '' 
    if doc_atend:
        print >> output_channel, ('\n\n' + delta.STATISTICS_DOC_STR)

def main():
    import optparse
    usage = """
%prog [options] 
run "%prog help" to list commands
examples:

python -m glance.compare info A.hdf
python -m glance.compare stats A.hdf B.hdf '.*_prof_retr_.*:1e-4' 'nwp_._index:0'
python -m glance.compare plotDiffs A.hdf B.hdf
python -m glance compare reportGen A.hdf B.hdf
python -m glance 

"""
    parser = optparse.OptionParser(usage)
    parser.add_option('-t', '--test', dest="self_test",
                    action="store_true", default=False, help="run internal unit tests")            
    parser.add_option('-q', '--quiet', dest="quiet",
                    action="store_true", default=False, help="only error output")
    parser.add_option('-v', '--verbose', dest="verbose",
                    action="store_true", default=False, help="enable more informational output")   
    parser.add_option('-w', '--debug', dest="debug",
                    action="store_true", default=False, help="enable debug output")   
    parser.add_option('-e', '--epsilon', dest="epsilon", type='float', default=0.0,
                    help="set default epsilon value for comparison threshold")   
    parser.add_option('-m', '--missing', dest="missing", type='float', default=None,
                    help="set default missing-value")
    #report generation related options
    parser.add_option('-p', '--outputpath', dest="outputpath", type='string', default='./',
                    help="set path to output directory")
    parser.add_option('-o', '--longitude', dest="longitudeVar", type='string',
                    help="set name of longitude variable")
    parser.add_option('-a', '--latitude', dest="latitudeVar", type='string',
                    help="set name of latitude variable")
    parser.add_option('-i', '--imagesonly', dest="imagesOnly", 
                      action="store_true", default=False,
                      help="generate only image files (no html report)")
    parser.add_option('-r', '--reportonly', dest="htmlOnly", 
                      action="store_true", default=False,
                      help="generate only html report files (no images)")
    parser.add_option('-c', '--configfile', dest="configFile", type='string', default=None,
                      help="set optional configuration file")
    parser.add_option('-l', '--llepsilon', dest='lonlatepsilon', type='float', default=0.0,
                      help="set default epsilon for longitude and latitude comparsion")
    parser.add_option('-n', '--version', dest='version',
                      action="store_true", default=False, help="view the glance version")
    parser.add_option('-f', '--fork', dest='doFork',
                      action="store_true", default=False, help="start multiple processes to create images in parallel")
    parser.add_option('-d', '--nolonlat', dest='noLonLatVars',
                      action="store_true", default=False, help="do not try to find or analyze logitude and latitude")
    
                    
    options, args = parser.parse_args()
    if options.self_test:
        import doctest
        doctest.testmod()
        sys.exit(2)

    lvl = logging.WARNING
    if options.debug: lvl = logging.DEBUG
    elif options.verbose: lvl = logging.INFO
    elif options.quiet: lvl = logging.ERROR
    logging.basicConfig(level = lvl)
    
    # display the version
    if options.version :
        print (_get_glance_version_string() + '\n')

    commands = {}
    prior = None
    prior = dict(locals())
    
    def info(*args):
        """list information about a list of files
        List available variables for comparison.
        """
        for fn in args:
            lal = list(io.open(fn)())
            lal.sort()
            print fn + ': ' + ('\n  ' + ' '*len(fn)).join(lal)
    
    def sdr_cris(*args):
        """compare sdr_cris output
        parameters are variable name followed by detector number
        sdr_cris desired.h5 actual.h5 ESRealLW 0
        """ # TODO ******* standardize with method?
        afn,bfn = args[:2]
        LOG.info("opening %s" % afn)
        a = io.open(afn)
        LOG.info("opening %s" % bfn)
        b = io.open(bfn)
        
        # shape is [scanline, field, detector, wnum]
        vname = '/All_Data/CrIS-SDR_All/' + args[2]
        det_idx = int(args[3])
        def get(f):
            spc = f[vname][:,:,det_idx,:]
            nsl,nfor,nwn = spc.shape
            return spc.reshape( (nsl*nfor,nwn) )
        aspc = get(a)
        bspc = get(b)
        plot.compare_spectra(bspc,aspc)
        plot.show()
    
    def noisecheck(*args):
        """gives statistics for dataset comparisons against truth with and without noise
        usage: noisecheck truth-file noise-file actual-file variable1{:epsilon{:missing}} {variable2...}
        glance noisecheck /Volumes/snaapy/data/justins/abi_graffir/coreg/pure/l2_data/geocatL2.GOES-R.2005155.220000.hdf.gz /Volumes/snaapy/data/justins/abi_graffir/noise/noise1x/l2_data/geocatL2.GOES-R.2005155.220000.hdf 
        """ # TODO ******* standardize with method?
        afn,noizfn,bfn = args[:3]
        LOG.info("opening truth file %s" % afn)
        a = io.open(afn)
        LOG.info("opening actual file %s" % noizfn)
        noiz = io.open(noizfn)
        LOG.info("opening noise file %s" % bfn)
        b = io.open(bfn)
        
        anames = set(a())
        bnames = set(b()) 
        cnames = anames.intersection(bnames) # common names
        pats = args[3:] or ['.*']
        names = _parse_varnames( cnames, pats, options.epsilon, options.missing )
        for name,epsilon,missing in names:
            aData = a[name]
            bData = b[name]
            nData = noiz[name]
            if missing is None:
                amiss = a.missing_value(name)
                bmiss = b.missing_value(name)
            else:
                amiss,bmiss = missing,missing
            x = aData
            y = bData
            z = nData
            def scat(x,xn,y):
                from pylab import plot,show,scatter
                scatter(x,y)
                show()
            nfo = delta.rms_corr_withnoise(x,y,z,epsilon,(amiss,bmiss),plot=scat)
            print '-'*32
            print name
            for kv in sorted(nfo.items()):
                print '  %s: %s' % kv
    
    def stats(*args):
        """create statistics summary of variables
        Summarize difference statistics between listed variables.
        If no variable names are given, summarize all common variables.
        Variable names can be of the form varname:epsilon:missing to use non-default epsilon or missing value.
        Variable names can be regular expressions, e.g. 'image.*' or '.*prof_retr.*::-999'
        Either epsilon or missing can be empty to stay with default.
        If _FillValue is an attribute of a variable, that will be used to find missing values where no value is given.
        Run with -v to get more detailed information on statistics.
        Examples:
         python -m glance.compare stats hdffile1 hdffile2
         python -m glance.compare stats --epsilon=0.00001 A.hdf B.hdf baseline_cmask_seviri_cloud_mask:0.002:
         python -m glance.compare -w stats --epsilon=0.00001 A.hdf A.hdf imager_prof_retr_abi_total_precipitable_water_low::-999
        """ 
        afn,bfn = args[:2]
        do_doc = (options.verbose or options.debug)
        
        tempOptions = { }
        tempOptions['epsilon']       = options.epsilon
        tempOptions['missing']       = options.missing
        # add more if needed for stats
        
        _ = stats_library_call(afn, bfn, var_list=args[2:],
                               options_set=tempOptions,
                               do_document=do_doc)

    def plotDiffs(*args) :
        """generate a set of images comparing two files
        This option creates a set of graphical comparisons of variables in the two given hdf files.
        The images detailing the differences between variables in the two hdf files will be
        generated and saved to disk. 
        Variables to be compared may be specified after the names of the two input files. If no variables
        are specified, all variables that match the shape of the longitude and latitude will be compared.
        Specified variables that do not exist, do not match the correct data shape, or are the longitude/latitude
        variables will be ignored.
        The user may also use the notation variable_name:epsilon:missing_value to specify the acceptible epsilon
        for comparison and the missing_value which indicates missing data. If one or both of these values is absent
        (in the case of variable_name:epsilon: variable_name::missing_value or just variable_name) the default value
        of 0.0 will be used for epsilon and no missing values will be analyzed. 
        The created images will be stored in the provided path, or if no path is provided, they will be stored in
        the current directory.
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used.
        Examples:
         python -m glance.compare plotDiffs A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         python -m glance.compare --outputpath=/path/where/output/will/be/placed/ plotDiffs A.hdf B.hdf
         python -m glance.compare plotDiffs --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
        """
        # set the options so that a report will not be generated
        options.imagesOnly = True
        
        # make the images
        reportGen(*args)
        
        return

    def reportGen(*args) :
        """generate a report comparing two files
        This option creates a report comparing variables in the two given hdf files.
        An html report and images detailing the differences between variables in the two hdf files will be
        generated and saved to disk. The images will be embedded in the report or visible as separate .png files.
        Variables to be compared may be specified after the names of the two input files. If no variables
        are specified, all variables that match the shape of the longitude and latitude will be compared.
        Specified variables that do not exist, do not match the correct data shape, or are the longitude/latitude
        variables will be ignored.
        The user may also use the notation variable_name:epsilon:missing_value to specify the acceptible epsilon
        for comparison and the missing_value which indicates missing data. If one or both of these values is absent
        (in the case of variable_name:epsilon: variable_name::missing_value or just variable_name) the default value
        of 0.0 will be used for epsilon and no missing values will be analyzed. 
        The html report page(s) and any created images will be stored in the provided path, or if no path is provided,
        they will be stored in the current directory.
        If for some reason you would prefer to generate the report without images, use the --reportonly option. This
        option will generate the html report but omit the images. This may be significantly faster, depending on
        your system, but the differences between the files may be quite a bit more difficult to interpret.
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used.
        Examples:
         python -m glance.compare reportGen A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         python -m glance.compare --outputpath=/path/where/output/will/be/placed/ reportGen A.hdf B.hdf
         python -m glance.compare reportGen --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
         python -m glance.compare reportGen --imagesonly A.hdf B.hdf
        """
        
        tempOptions = { }
        tempOptions['outputpath']    = options.outputpath
        tempOptions['configFile']    = options.configFile
        tempOptions['imagesOnly']    = options.imagesOnly
        tempOptions['htmlOnly']      = options.htmlOnly
        tempOptions['doFork']        = options.doFork
        tempOptions['noLonLatVars']  = options.noLonLatVars
        tempOptions['latitudeVar']   = options.latitudeVar
        tempOptions['longitudeVar']  = options.longitudeVar
        tempOptions['lonlatepsilon'] = options.lonlatepsilon
        tempOptions['epsilon']       = options.epsilon
        tempOptions['missing']       = options.missing
        
        reportGen_library_call(args[0], args[1], args[2:], tempOptions)
    
    """
    # This was used to modify files for testing and should not be uncommented
    # unless you intend to use it only temporarily for testing purposes
    # at the moment it is not written very generally (only works with hdf4),
    # requires you to use 'from pyhdf.SD import SD, SDS' and change io to load
    # files in write mode rather than read only
    def make_renamed_variable_copy(*args) :
        '''
        make a copy of a variable in a file using the new name given by the user
        '''
        file_path = args[0]
        old_var_name = args[1]
        new_var_name = args[2]
        
        print ("Copying variable \'" + old_var_name + "\' to \'" + new_var_name
               + "\' in file " + file_path)
        
        # open the file and get the old variable
        LOG.info("\topening " + file_path)
        file_object = io.open(file_path)
        LOG.info("\tgetting " + old_var_name)
        variable_object_old = file_object.get_variable_object(old_var_name)
        temp, old_rank, old_shape, old_type, old_num_attributes = SDS.info(variable_object_old)
        old_attributes = SDS.attributes(variable_object_old)
        
        # make a copy of the variable with the new name
        LOG.info("\tsaving " + new_var_name)
        variable_object_new = SD.create(file_object, new_var_name, old_type, old_shape)
        SDS.set(variable_object_new, variable_object_old[:])
        '''  TODO, attribute copying is not working yet
        for attribute_name in old_attributes :
            variable_object_new[attribute_name] = variable_object_old[attribute_name]
        '''
        
        # close up all our access objects
        SDS.endaccess(variable_object_old)
        SDS.endaccess(variable_object_new)
        SD.end(file_object)
        
        return
    """

    # def build(*args):
    #     """build summary
    #     build extended info
    #     """
    #     LOG.info("building database tables")
    #     
    # def grant(*args):
    #     """grant summary
    #     grant extended info
    #     """
    #     LOG.info("granting permissions for tables")
    #     
    # def index(*args):
    #     """index summary
    #     index extended info
    #     """
    #     LOG.info("creating indices for tables")
        
    def help(command=None):
        """print help for a specific command or list of commands
        e.g. help stats
        """
        if command is None: 
            # print first line of docstring
            for cmd in commands:
                ds = commands[cmd].__doc__.split('\n')[0]
                print "%-16s %s" % (cmd,ds)
        else:
            print commands[command].__doc__
            
    # def test():
    #     "run tests"
    #     test1()
    #     
    commands.update(dict(x for x in locals().items() if x[0] not in prior))    
    
    if (not args) or (args[0] not in commands): 
        parser.print_help()
        help()
        return 9
    else:
        locals()[args[0]](*args[1:])

    return 0


if __name__=='__main__':
    sys.exit(main())