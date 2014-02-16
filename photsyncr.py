import configparser
import json
import logging.config
import time
import sys
import os.path
import argparse
import itertools
import flickrapi

settings = {}

def loadSettings():
    try:
        configfile = 'settings.conf'
        config = configparser.ConfigParser()
        config.read(configfile)
        settings = config.defaults()
    
        if 'imagedir' not in settings:
            raise Exception("Config property 'imagedir' in section '[DEFAULT]' of 'settings.conf' must be set")
        
        if not os.path.isdir(settings['imagedir']):
            raise Exception("The image directory '" + settings['imagedir'] + "' does not exist")
    
        logging.debug("Loaded settings %s from %s", settings, configfile)
        return settings
    except Exception as error:
        logging.error(error)
        sys.exit(2)

def scanDirectories(imagedir):
    directories = {}
    logging.debug("Scanning %s recursively for files with extension .jpg", imagedir)
    for root, _, files, dirfd in os.fwalk(imagedir):
        filepairs = set()
        if (".skipsync" in files):
            logging.debug("Skip synchronization of %s", root)
            continue
        for file in files:
            extension = file.split(".")[-1].lower()
            if (extension == "jpg"):
                filepairs.add((file, os.stat(file, dir_fd=dirfd).st_size))
        if len(filepairs) > 0:
            directories[root] = filepairs
    return directories

def compareDirectories(directories):
    logging.debug("Comparing files in folder pairs for duplicate name and size combinations")    
    dupedirs = {}
    combinations = itertools.combinations(directories, 2)
    for (dir1, dir2) in combinations:
        logging.debug("Comparing %s with %s", dir1, dir2)
        duplicates = directories[dir1] & directories[dir2]
        if len(duplicates) > 0:
            dupedirs[(dir1, dir2)] = duplicates
    return dupedirs

def printDupes(dupedirs, directories):
    sorteddupes = sorted(dupedirs.items(), key=lambda t: len(t[1]), reverse=True)
    for (dupedir, files) in sorteddupes:
        (dir1, dir2) = dupedir
        logging.info("%s of %s/%s duplicates in %s and %s", len(files), len(directories[dir1]), len(directories[dir2]), dir1, dir2)
        if (logging.root.isEnabledFor(logging.DEBUG)):
            for file in files:
                logging.debug("Duplicate (file,size): %s", file)
    if len(sorteddupes) == 0:
        logging.info("No duplicate files found")
        
def upload(directories):
    for directory in directories:
        logging.debug(directory)
        for (file, _) in directories[directory]:
            uploadImage(os.path.join(directory, file))

def uploadImage(file):
    logging.debug("Uploading image %s", file)
    flickr = flickrapi.FlickrAPI("ca4f6933e5e33581d9e0f8c5324190e8", "b2971103378e60de")
    flickr.flickr_oauth.get_request_token("oob")
    authorize_url = flickr.flickr_oauth.auth_url(perms='write')
    print("Go to the following link in your browser to authorize this application:")
    print(authorize_url)
    print()
    flickr.flickr_oauth.verifier = input('Enter the verifier: ')
    token = flickr.flickr_oauth.get_access_token()
    logging.debug("Token=%s",token)
    flickr.token_cache.token = token 
    flickr.upload(file)

def reportDuplicates(imagedir):
    directories = scanDirectories(imagedir)
    dupedirs = compareDirectories(directories)
    printDupes(dupedirs, directories)

if __name__ == "__main__":
    # Set up logging
    config = json.load(open('logging.conf'))
    logging.config.dictConfig(config)
    
    settings = loadSettings()
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--dupe-report', action='store_true', help='Find and report duplicate photos')
    args = parser.parse_args()
    if (args.dupe_report):
        reportDuplicates(settings['imagedir'])
        sys.exit(0)

    start = time.time()
    directories = scanDirectories(settings['imagedir'])
    logging.debug("Found %s directories with images", len(directories))
    
    upload(directories)
        
    logging.info("Sync ended after %s seconds", time.time() - start)