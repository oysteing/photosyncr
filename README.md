photosyncr
==========

## Overview
photosyncr is a command-line batch uploader for Flickr

## Prerequisites
- Python 3.x
- flickrapi python module (https://pypi.python.org/pypi/flickrapi)

## Features
- Duplicate report - identify files with identical name and size across directories
- Upload - Recursively update all photos (.jpg) from a tree of folders

## Configuration
Edit `settings.conf` and set imagedir to the top level directory you want to synchronize. Example:
	[DEFAULT]
	imagedir = /images
	
## Usage
	python photosyncr.py