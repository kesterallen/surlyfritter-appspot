
import datetime
import re
import math
import EXIF
import logging
import StringIO
from pprint import pformat

from google.appengine.api import images
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import blobstore

IMAGE_SIZE = 1000

def str_to_dt(datestring):
    """Convert a string date of the formats:
            YYYY:MM:DD HH:mm:ss foo:asdf-bar.asdf.4312-_asdf
            YYYY:MM:DD HH:mm:ss
            YYYY:MM:DD HH:mm
            YYYY:MM:DD HH
            YYYY:MM:DD
            YYYY MM DD HH mm ss foo:asdf-bar.asdf.4312-_asdf
            YYYY MM DD HH mm ss
            YYYY MM DD HH mm
            YYYY MM DD HH
            YYYY MM DD
    to a datetime.datetime object.
    """
    str_arr = re.split('[: ]', datestring)

    # Take up to the first 6 elements, ignoring extra elements:
    if len(str_arr) > 6:
        nelements = 6
    else:
        nelements = len(str_arr)
    date_arr = [int(d) for d in str_arr[:nelements]]

    dt = datetime.datetime(*date_arr)
    return dt


# TODO: Memcache name generation:
#
class memcachingParent(db.Model):
    def get_memcache_name(self, *args):
        """Return a unique memcache name based on the object's class, the user,
        and the extra args given."""

        user = users.get_current_user()
        if user is None:
            username = ''
        else:
            username = user.nickname()

        memcache_name_parts = [self.__class__.__name__, username]
        logging.info("memcache_name_parts %s" % memcache_name_parts)

        for arg in args:
            memcache_name_parts.append(arg)
        
        logging.info("memcache_name_parts %s" % memcache_name_parts)    
        memcache_name = "".join(memcache_name_parts)
        return memcache_name

# Data Models:
#
class Picture(db.Model):
    date = db.DateTimeProperty(auto_now_add=True)
    name = db.StringProperty(multiline=True)
    picture = db.BlobProperty()
    blobStorePictureKey = blobstore.BlobReferenceProperty()

    def __str__(self):
        return "%s %s" % (self.date, 
                          self.name,)
                             #self.picture,)
                                #self.blobStorePictureKey)

    @property
    def is_good(self):
        """This picture contains data which can be displayed as an image."""
        return self.picture is not None or \
               self.blobStorePictureKey is not None

    def timeString(self):
        timeString = "%d%02d%02d%02d%02d%02d" % (
                     self.date.year, self.date.month, self.date.day, 
                     self.date.hour, self.date.minute, self.date.second)
        return timeString

    def timeStringExivFormat(self):
        timeString = "%d:%02d:%02d %02d:%02d:%02d" % (
                      self.date.year, self.date.month, self.date.day, 
                      self.date.hour, self.date.minute, self.date.second)
        return timeString

    def setPictureAndName(self, image, name, isBlobstore=False):
        logging.info(
            "start Picture.setPictureAndName, name %s, isBlobstore %s" % 
            (name, isBlobstore))
        self.setPicture(image, isBlobstore)
        self.setName(name)
        logging.info(
            "done with Picture.setPictureAndName, name %s, isBlobstore %s" % 
            (name, isBlobstore))

    def setPicture(self, decodedImage, isBlobstore=False):
        logging.info("starting setPicture, isBlobstore=%s" % isBlobstore)
        if isBlobstore:
            logging.info("setPicture: blobStorePictureKey = %s" % decodedImage)
            self.blobStorePictureKey = decodedImage
            self.picture = None
        else:
            self.picture = decodedImage
            self.blobStorePictureKey = None
        logging.info("setting date in setPicture")
        self.setDateFromImageTags()
        logging.info("done setting date in setPicture")

    def setName(self, nameSuffix):
        logging.info("starting setName, nameSuffix = %s" % nameSuffix)
        self.name = self.timeString() + nameSuffix
        logging.info("done with setName, name = %s" % self.name)

    def getExivTags(self, image=None):
        if image is not None:
            image_file = StringIO.StringIO(image)
        elif self.picture is not None:
            image_file = StringIO.StringIO(self.picture)
        elif self.blobStorePictureKey is not None:
            blob_reader = blobstore.BlobReader(self.blobStorePictureKey)
            pictureBlob = blob_reader.read()
            image_file = StringIO.StringIO(pictureBlob)
        else:
            logging.error("Picture type error in getExivTags")
            image_file = None

        if image_file is None:
            exiv_tags = None
        else:
            exiv_tags = EXIF.process_file(image_file)

        return exiv_tags

    def getRotatedImage(self):
        """ Returns the image, rotated if necessary. If rotation is not
        necessary, nothing is done.  
        """
        #TODO: use the exiv data to resize the images to a consistent max size (1200?)?
        if self.picture is not None:
            image = self.picture
            logging.debug("getRotatedImage: image is from self.picture")
        elif self.blobStorePictureKey is not None:
            blob_reader = blobstore.BlobReader(self.blobStorePictureKey)
            image = blob_reader.read()
            logging.debug("getRotatedImage: image is a blobstore image")
        else:
            logging.debug("getRotatedImage: NO IMAGE")

        exivTags = self.getExivTags(image)


        if "Image Orientation" in exivTags:
            logging.debug("image orientation is in exivTags")
            orientation = str(exivTags["Image Orientation"])
            logging.debug("orientation in exivTags is: %s" % orientation)

            if orientation == "Rotated 180": # 3
                image = images.rotate(image, 180, images.JPEG)
            elif orientation == "Rotated 90 CW": # 6
                image = images.rotate(image, 90, images.JPEG)
            elif orientation == "Rotated 90 CCW": # 8
                image = images.rotate(image, 270, images.JPEG)
            else:
                logging.debug(
                    "orientation is %s, returning without performing rotation" 
                    % orientation)
        else:
            logging.debug("image orientation tag not present in %s" % 
                          self.name)

        return image

    def getImage(self):
        memcacheName = "image%s" % self.name
        image = memcache.get(memcacheName)
        if image is None:
            logging.debug("No Picture.getImage in memcache for %s" % memcacheName)
            image = self.getRotatedImage()
            memcacheStatus = memcache.set(memcacheName, image)
            if not memcacheStatus:
                logging.debug("Picture.getImage memcache set failed for %s" % 
                              memcacheName)
            else:
                logging.debug("Picture.getImage memcache set succeeded for %s" % 
                               memcacheName)
        else:
            logging.debug("Picture.getImage memcache get succeeded for %s" % 
                          memcacheName)
        return image

    def getDateRaw(self):
        exivTags = self.getExivTags()
        if 'Image DateTime' in exivTags:
            imageTime = str(exivTags['Image DateTime'])
            logging.debug("getting imageTime from exivTags %s" % imageTime)
            if imageTime == '':
                imageTime = self.timeStringExivFormat()
                logging.debug(
                    "getting imageTime on second pass from "
                    "self.timeStringExivFormat %s" % imageTime)
        else:
            imageTime = self.timeStringExivFormat()
            logging.debug("Picture.getDateRaw(): getting imageTime from self.timeStringExivFormat %s" % imageTime)

        if not imageTime:
            imageTime = "1999:01:01 01:01:01"

        return imageTime

    def isExivDate(self):
        exivTags = self.getExivTags()
        return 'Image DateTime' in exivTags

    def getDate(self, is_compact=False):
        if is_compact:
            rawDate = self.getDateRaw()
            date = datetime.datetime(*[int(i) for i in re.split("[: ]", rawDate)])
            logging.debug("Picture.getDate(is_compact=True): rawDate %s, date %s" % (rawDate, date))
            return date
        else:
            preface = "Date: " if self.isExivDate() else "Uploaded date: "
            date = self.getDateRaw()
            return preface + date

    def setDateFromImageTags(self):
        imageTime = self.getDateRaw()
        self.date = datetime.datetime.strptime(imageTime, "%Y:%m:%d %H:%M:%S")

class PictureIndex(db.Model):
    count = db.IntegerProperty()
    dateOrderIndex = db.IntegerProperty()
    pix_ref = db.ReferenceProperty(Picture)
    dateOrderString = db.StringProperty()

    defaultDate = '2007:10:26 05:30:00'

    @classmethod
    def make_picture_index(cls, picture, count, dateOrderIndex, dateOrderString):
        picture_index = PictureIndex()
        picture_index.pix_ref = picture
        picture_index.count = count
        picture_index.dateOrderIndex = dateOrderIndex
        picture_index.dateOrderString = dateOrderString
        logging.info("Making PictureIndex object: %s" % picture_index)
        return picture_index
            
    @classmethod
    def memcacheName(cls, index, by_date):
        username = users.get_current_user()
        template = "PictureIndexByDate%s%s" if by_date else "PictureIndex%s%s"
        name = template % (index, username)
        return name

    @classmethod
    def dateOrderIndexToCount(cls, dateOrderIndex):
        pictureIndex = PictureIndex.get(dateOrderIndex, by_date=True)
        if pictureIndex is None:
            pictureIndex = PictureIndex.all().order('-count').get()
        if pictureIndex is not None:
            return pictureIndex.count
        else:
            return 0

    @classmethod
    def countToDateOrderIndex(cls, count):
        pictureIndex = PictureIndex.get(count, by_date=False)
        if pictureIndex is None:
            pictureIndex = PictureIndex.all().order('-dateOrderIndex').get()
        return pictureIndex.dateOrderIndex

    @classmethod
    def get(cls, index, by_date=True):
        """Return the index-th PictureIndex, either by count or by
        dateOrderIndex."""

        index = int(float(index))
        name = PictureIndex.memcacheName(index, by_date)
        #name = get_memcache_name(PictureIndex, by_date=by_date)
        pictureIndex = memcache.get(name)
        if pictureIndex is None:
            logging.info("No memcache result for %s. Extracting "
                         "PictureIndex for index %s with by_date %s" % 
                            (name, index, by_date))
            if by_date:
                pictureIndex = PictureIndex.all().filter(
                                    'dateOrderIndex', index).get()
            else:
                pictureIndex = PictureIndex.all().filter('count', index).get()
                logging.info("PI %s" % pictureIndex)

            logging.info("Memcaching the PictureIndex %s result: %s" % 
                         (name, pformat(pictureIndex)))
            memcacheStatus = memcache.set(name, pictureIndex)
            if not memcacheStatus:
                logging.debug("memcaching failed in PictureIndex.get")
        else:
            logging.debug("memcache worked in PictureIndex.get %s %s" % 
                            (name, pformat(pictureIndex)))
        return pictureIndex

    def __str__(self):
        msg = ('count: %s, dateOrderndex: %s, dateOrderString: %s' % 
                (self.count, self.dateOrderIndex, self.dateOrderString))
        return msg

    @property
    def tags(self):
        return Tag.getTagNames(self.count)

    @property
    def comments(self): 
        return PictureComment.getCommentsString(self.count)

    @property
    def datetime(self):
        return str_to_dt(self.dateOrderString)

    @property
    def img_url(self):
        try:
            blob_key = self.pix_ref.blobStorePictureKey
            url = images.get_serving_url(blob_key, size=IMAGE_SIZE)
        except Exception as err:
            logging.debug("Error in PictureIndex.img_url: %s", err)
            url = '/img/%s' % self.dateOrderIndex

        return url

    def template_repr(self):
          pi_dict = {
              'dateOrderIndex': self.dateOrderIndex,
              'img_url': self.img_url,
              'comments': self.comments,
              'tags': self.tags,
              'datetime': self.datetime,
          }
          return pi_dict

class Greeting(db.Model):
    author = db.UserProperty()
    content = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)

class UserFavorite(db.Model):
    date = db.DateTimeProperty(auto_now_add=True)
    user = db.UserProperty()
    picture_index = db.ReferenceProperty(PictureIndex)

class PictureComment(db.Model):
    date = db.DateTimeProperty(auto_now_add=True)
    author = db.UserProperty()
    content = db.StringProperty(multiline=True)
    picture_index = db.IntegerProperty()

    @classmethod
    def memcacheName(cls, index):
        username = users.get_current_user()
        name = "picture_comment_%s%s" % (index, username)
        return name

    @classmethod
    def getComments(cls, index):
        memcacheName = PictureComment.memcacheName(index)
        #memcacheName = get_memcache_name(PictureComment, index=index)
        comments = memcache.get(memcacheName)
        if comments is None:
            logging.info("Running PictureComment.all()")
            comments = PictureComment.all().filter('picture_index', index)

            memcacheStatus = memcache.set(memcacheName, comments)
            if not memcacheStatus:
                logging.debug(
                    "memcaching failed in PictureComment.getComments")
        else:
            logging.debug("memcache worked in PictureComment.getComments %s %s"
                          % (memcacheName, comments))
        
        return comments

    @classmethod
    def getCommentsString(cls, index):
        if index is None:
            index = 0
        comments = PictureComment.getComments(index)
        if comments is None:
            displayCommentText = ""
        else:
            displayCommentText = " ".join(
                                    [comment.content for comment in comments])
        return displayCommentText

class UniqueTagName(db.Model):
    name = db.StringProperty()
    tag_count = db.IntegerProperty()

    def fontsize(self):
        if self.tag_count < 5:
            fontsize = 10
        elif self.tag_count < 10:
            fontsize = 13
        elif self.tag_count < 20:
            fontsize = 16
        elif self.tag_count < 40:
            fontsize = 19
        elif self.tag_count < 120:
            fontsize = 22
        else:
            fontsize = 25
        return fontsize

    @classmethod
    def updateTagCounts(cls):
        for unique_tag_name in UniqueTagName.all():
            count = Tag.all().filter('name_ref', unique_tag_name).count()
            unique_tag_name.tag_count = count
            unique_tag_name.put()

    @classmethod
    def getTagCounts(cls):
        counts = {}
        for unique_tag_name in UniqueTagName.all():
            counts[str(unique_tag_name.name)] = tag.tag_count
        return counts

class Tag(db.Model):
    date = db.DateTimeProperty(auto_now_add=True)
    count = db.IntegerProperty()
    name_ref = db.ReferenceProperty(UniqueTagName)

    @classmethod
    def memcacheName(cls, index):
        username = users.get_current_user()
        name = "tags_for_%s%s" % (index, username)
        return name

    @classmethod
    def getTagNames(cls, index):
        memcacheName = Tag.memcacheName(index)
        #memcacheName = get_memcache_name(Tag, index=index)
        tag_names = memcache.get(memcacheName)
        if tag_names is None:
            logging.info("Running Tag.getTagNames()")
            tags = Tag.all().filter('count', index)
            tag_names = [str(tag.name_ref.name) for tag in tags]

            memcacheStatus = memcache.set(memcacheName, tag_names)
            if not memcacheStatus:
                logging.debug("memcaching failed in Tag.getTagNames")
        else:
            logging.debug("memcache worked in Tag.getTagNames: %s %s" % (
                           memcacheName, tag_names))

        logging.debug("Tag names are (%s) %s" % (len(tag_names), tag_names))
        return tag_names

    @classmethod
    def getIndicesByName(cls, name):
        unique_tags = UniqueTagName.all().filter('name', name)
        if unique_tags.count(limit=1) == 0:
            return ['no tags with name %s' % name]

        tag_results = Tag.all().filter('name_ref', unique_tags[0].key())
        tags = ["<p>%s<br>%s</p>" % 
                    (tag.name_ref.name, tag.count) for tag in tag_results]
        tags.append("<p><hr>Unique name:%s" % unique_tags[0].name)
        return tags

    @classmethod
    def getTagsString(cls, index):
        tag_names = Tag.getTagNames(index)
        if tag_names:
            displayTagText = ' '.join(tag_names)
        else:
            displayTagText = ''
        return displayTagText
