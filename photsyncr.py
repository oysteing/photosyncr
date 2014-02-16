import ConfigParser
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
        config = ConfigParser.ConfigParser()
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
    for root, _, files in os.walk(imagedir):
        filepairs = set()
        if (".skipsync" in files):
            logging.debug("Skip synchronization of %s", root)
            continue
        for filename in files:
            extension = filename.split(".")[-1].lower()
            if (extension == "jpg"):
                filepairs.add((filename, os.stat(os.path.join(root, filename)).st_size))
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
            for filename in files:
                logging.debug("Duplicate (file,size): %s", filename)
    if len(sorteddupes) == 0:
        logging.info("No duplicate files found")

def reportDuplicates(imagedir):
    directories = scanDirectories(imagedir)
    dupedirs = compareDirectories(directories)
    printDupes(dupedirs, directories)

class Flickr:
    
    def __init__(self):
        self.flickr = flickrapi.FlickrAPI("ca4f6933e5e33581d9e0f8c5324190e8", "b2971103378e60de")
        self.flickr.authenticate_console(perms='write')
        
    def upload(self, directories):
        for directory in directories:
            logging.debug(directory)
            photos = []
            for (filename, _) in directories[directory]:
                photos.append(self.uploadImage(os.path.join(directory, filename)))
            self.createPhotoset(directory, photos)
    
    def uploadImage(self, filename):
        logging.debug("Uploading image %s", filename)
        rsp = self.flickr.upload(filename)
        return rsp.find('photoid').text
        
    def createPhotoset(self, directory, photos):
        title = os.path.basename(directory)
        logging.debug("Creating photoset %s", title)
        rsp = self.flickr.photosets_create(title=title, primary_photo_id=photos[0])
        photosetid = rsp.find('photoset').attrib['id'] 
        self.flickr.photosets_editPhotos(photoset_id=photosetid, primary_photo_id=photos[0], photo_ids=",".join(photos))        

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
    
    Flickr().upload(directories)
        
    logging.info("Sync ended after %s seconds", time.time() - start)