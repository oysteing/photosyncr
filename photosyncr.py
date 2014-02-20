import ConfigParser
import json
import logging.config
import time
import sys
import os.path
import argparse
import itertools
import flickrapi
import shelve
import xml.etree.ElementTree as ET

settings = {}
extensions = ('jpg', 'jpeg', 'png', 'gif')

def loadSettings():
    try:
        configfile = 'settings.conf'
        config = ConfigParser.ConfigParser()
        config.read(configfile)
        settings = config.defaults()
    
        if 'photodir' not in settings:
            raise Exception("Config property 'photodir' in section '[DEFAULT]' of 'settings.conf' must be set")
        
        if not os.path.isdir(settings['photodir']):
            raise Exception("The image directory '" + settings['photodir'] + "' does not exist")
        
        if 'cachefile' not in settings:
            settings['cachefile'] = os.path.expanduser('~/.photosyncr_cache')
            
        logging.debug("Loaded settings %s from %s", settings, configfile)
        return settings
    except Exception as error:
        logging.error(error)
        sys.exit(2)

def scanDirectories(photodir):
    directories = {}
    logging.debug("Scanning %s recursively for files with extensions %s", photodir, extensions)
    for root, _, files in os.walk(photodir):
        images = set()
        if ".skipsync" in files:
            logging.debug("Skip synchronization of %s", root)
            continue
        for filename in files:
            extension = filename.split(".")[-1].lower()
            if extension in extensions:
                images.add(filename)
        if len(files) > 0:
            directories[root] = images
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
        if logging.root.isEnabledFor(logging.DEBUG):
            for filename in files:
                logging.debug("Duplicate (file): %s", filename)
    if len(sorteddupes) == 0:
        logging.info("No duplicate files found")

def reportDuplicates(photodir):
    directories = scanDirectories(photodir)
    dupedirs = compareDirectories(directories)
    printDupes(dupedirs, directories)
    
def reportIgnoredFiles(photodir):
    logging.debug("Scanning %s recursively for files with extensions other than %s", photodir, extensions)
    for root, _, files in os.walk(photodir):
        if ".skipsync" in files:
            logging.debug("Skip synchronization of %s", root)
            continue
        for filename in files:
            extension = filename.split(".")[-1].lower()
            if extension not in extensions:
                print(filename)
    
class Flickr:
    
    def __init__(self):
        self.flickr = flickrapi.FlickrAPI("ca4f6933e5e33581d9e0f8c5324190e8", "b2971103378e60de")
        self.flickr.authenticate_console(perms='write')

    @property        
    def photosets(self):
        if not hasattr(self, '_photosets'):
            # TODO support pagination
            rsp = self.flickr.photosets_getList(user_id='112746106@N06')
            photosets = {}
            for photoset in rsp.findall('photosets/photoset'):
                photosets[photoset.find('title').text] = photoset.attrib['id']
            self._photosets = photosets
            logging.debug("Found %s existing photosets", photosets)
        return self._photosets
        
    def upload(self, directories):
        for directory in directories:
            photos = []
            for filename in directories[directory]:
                path = os.path.join(directory, filename)
                photoid = self.uploadImage(path)
                photos.append((path, photoid))
            self.createPhotoset(directory, [photo[1] for photo in photos])
            cacheNewPhotos(directory[len(settings['photodir']):], directories[directory])
    
    def uploadImage(self, path):
        photoTag = '#' + path.replace(' ', '#')[len(settings['photodir']):]
        logging.debug("Uploading image %s with tag %s", path, photoTag)
        rsp = self.flickr.upload(path, tags=photoTag)
        return rsp.find('photoid').text
        
    def createPhotoset(self, directory, photos):
        title = os.path.basename(directory)
        if title in self.photosets:
            for photo in photos:
                photosetid = self.photosets[title]
                logging.debug("Adding photo %s to photoset %s (%s)", photo, title, photosetid)
                self.flickr.photosets_addPhoto(photoset_id=photosetid, photo_id=photo)
        else:
            logging.debug("Creating photoset %s with %s photos", title, len(photos))
            rsp = self.flickr.photosets_create(title=title, primary_photo_id=photos[0])
            photosetid = rsp.find('photoset').attrib['id']
            self.flickr.photosets_editPhotos(photoset_id=photosetid, primary_photo_id=photos[0], photo_ids=",".join(photos))
        
    def deleteAll(self):
        self.flickr.authenticate_console(perms='delete')
        rsp = self.flickr.photos_search(user_id='me')
        pages = int(rsp.find('photos').attrib['pages'])
        self.deletePhotos(rsp.findall('photos/photo'))
        for page in range(2, pages+1):
            rsp = self.flickr.photos_search(user_id='me', page=page)
            self.deletePhotos(rsp.findall('photos/photo'))
        if os.path.isfile(settings['cachefile']):
            os.remove(settings['cachefile'])
            logging.info("Removed cachefile %s", settings['cachefile'])

    def deletePhotos(self, photos):
        for photo in photos:
            self.flickr.photos_delete(photo_id=photo.attrib['id'])
            logging.info("Deleted photo %s", photo.attrib['id'])

    def checkCache(self):
        cachesize = 0
        if os.path.exists(settings['cachefile']):
            cache = shelve.open(settings['cachefile'], flag='r')
            cachesize
            for directory in cache.keys():
                photos = cache[directory]
                cachesize += len(photos)
        rsp = self.flickr.photos_search(user_id='me')
        flickrsize = int(rsp.find('photos').attrib['total'])
        logging.debug("Checking cache freshness against Flickr. Cache has %s entries, Flickr account %s", cachesize, flickrsize)
        if cachesize != flickrsize:
            logging.error("Cache is not in sync with Flickr account. Please synchronize")
            return False
        return True

def relativeDirectory(directory):
    return directory[len(settings['photodir']):]

def removeCached(directories):
    if not os.path.exists(settings['cachefile']):
        return directories
    cache = shelve.open(settings['cachefile'], flag='r')
    newDirectories = {}
    for directory in directories:
        reldir = relativeDirectory(directory)
        cached = cache[reldir]
        logging.debug("Found cached photos in %s: %s. Removing from upload set %s", reldir, cached, directories[directory])
        photos = directories[directory] - cached
        if len(photos) > 0:
            newDirectories[directory] = photos
    cache.close()
    logging.debug("Kept %s of %s directories with images after removing cached (already uploaded) entries", len(newDirectories), len(directories))
    return newDirectories

def cacheNewPhotos(reldir, newPhotos):
    cache = shelve.open(settings['cachefile'])
    if reldir in cache:
        directory = cache[reldir]
        directory = directory | newPhotos
        cache[reldir] = directory
    else:
        cache[reldir] = newPhotos
    cache.close()

if __name__ == "__main__":
    # Set up logging
    config = json.load(open('logging.conf'))
    logging.config.dictConfig(config)
    
    settings = loadSettings()
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--dupe-report', action='store_true', help='Find and report duplicate photos in local filesystem')
    parser.add_argument('--ignored-report', action='store_true', help='Find and report files not recongized as photos')
    parser.add_argument('--delete-all', action='store_true', help='Delete all photos in Flickr account')
    args = parser.parse_args()
    if args.dupe_report:
        reportDuplicates(settings['photodir'])
        sys.exit(0)
    elif args.ignored_report:
        reportIgnoredFiles(settings['photodir'])
        sys.exit(0)
    elif args.delete_all:
        Flickr().deleteAll()
        sys.exit(0)

    start = time.time()
    directories = scanDirectories(settings['photodir'])
    logging.debug("Found %s directories with images", len(directories))

    flickr = Flickr()
    if flickr.checkCache():
        directories = removeCached(directories)    
        flickr.upload(directories)
        
    logging.info("Sync ended after %s seconds", time.time() - start)