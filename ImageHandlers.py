
import logging

from google.appengine.ext import webapp
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.api import memcache

from utils import (render_template_text, highest_index_value, 
                   highest_picture_index, highest_index_by_date)
import re

from Parents import RequestHandlerParent
from TimeJumpHandlers import TimeJumpHandler, MiriTimeJumpHandler
from DataModels import (Picture, PictureIndex, Greeting, UserFavorite,
                        PictureComment, UniqueTagName, Tag, str_to_dt)

class ReplaceImageHandler(webapp.RequestHandler):
    def get(self):
        template_text = render_template_text('replace_picture.html', {})
        self.response.out.write(str(template_text))

    def post(self):
        count = int(self.request.get('count'))
        new_pic = self.request.POST.get('file_to_upload').file.read()

        #TODO: remove old Picture object (and blob if applicable):
        picture_index = PictureIndex.all().filter('count', count).get()
        picture_index.pix_ref.setPicture(new_pic)
        picture_index.pix_ref.put()

        memcache.flush_all()
        self.response.out.write(str("uploaded new pic to %s" % count))

class ImageServingUrl(webapp.RequestHandler):
    """Not used in production. This is a method to test that the pi.img_url is
    generating the correct URLs, especially for the Cloud Storage objects."""
    def get(self, index=None):
        pi = PictureIndex.get(index, byDate=False)
        self.response.out.write(pi.img_url)

class ImageParent(RequestHandlerParent,
                  blobstore_handlers.BlobstoreDownloadHandler):
    """
    This parent class encapsulates writing the image out to the HTTP response.
    It is a RequestHandlerParent child class because it needs the self.response
    member.
    """
    def _handleImageInternal(self, picture):
        if picture:
            if picture.is_good:
                self.response.headers['Content-Type'] = "image/jpg"
                self.write_output(picture.getImage())
            else:
                logging.debug('404ing -- no image in Picture object')
                self.error(404)
        else:
            logging.debug('404ing -- no Picture entity')
            self.error(404)

    def handleImageByName(self, name):
        picture = Picture.all().filter('name', name).get()
        self._handleImageInternal(picture)

    def handleImage(self, index, by_date=True):
        index = self.validate_index(index, check_bounds=by_date)

        picture_index = PictureIndex.get(index=index, by_date=by_date)
        if picture_index is None:
            self.write_output("Picture indexing error for index %s!" % index)
        else:
            picture = picture_index.pix_ref
            self._handleImageInternal(picture)

class ImageByDateHandler(TimeJumpHandler):
    def get(self, date_str=None):
        picture_index = self.get_index_from_date(date_str)
        self.redirect('/imgperm/%d' % picture_index.count)

class ImageByJpgIndexHandler(ImageParent):
    def get(self):
        url = self.request.url
        m = re.search('\D*(\d+)\.jpg', url)
        if m is None:
            self.error(404)
            return
        count = self.get_index(m.group(1), check_bounds=False)

        self.handleImage(count, by_date=False)

class ImageByNameHandler(ImageParent):
    def get(self, name=None):
        self.handleImageByName(name)

class ImageByOrderAddedHandler(ImageParent):
    def get(self, index=None):
        check_bounds = False
        self.handleImage(index, by_date=check_bounds)

class ImageByIndexHandler(ImageParent):
    def get(self, index=None):
        check_bounds = True
        self.handleImage(index, by_date=check_bounds)

class FilmstripHandler(ImageParent):
    def get_filmstrip_indices(self, num_pics, current_index=None):
        """
        Get the PictureIndex objects for a filmstrip.

        If current_index is specified, return the num_pics previous pictures
        (including current_index). If current_index is None, return a random
        set of pictures, taken from a uniformly-sampled set of timepoints
        instead of a random set of indices. Random indices, which I had
        previously, favor times with more pictures in them.
        """

        is_random = (current_index is None)
        if is_random:
            tjh = TimeJumpHandler()
            pis = []
            for i in range(num_pics):
                rand_dt = MiriTimeJumpHandler.random_datetime_since_birth()
                index = tjh.get_index_from_date(str(rand_dt))
                pis.append(index)
        else:
            indices = [current_index-i for i in range(num_pics)]
            pis = [PictureIndex.get(index, by_date=False) for index in indices]

        return pis

    def get_filmstrip_html(self, current_index, num_pics=20):
        num_pics_request= self.request.get('slidecount')
        if num_pics_request:
            num_pics = int(float(num_pics_request))

        logging.info("num_pics = %s" % num_pics)
        pictureIndices = []

        for index in self.get_filmstrip_indices(num_pics, current_index):
            if pi:
                logging.info("PictureIndex.get(%d) returns %s" % (index, pi))
                count = PictureIndex.dateOrderIndexToCount(index)
                tmpText = "%s %s %s" % (PictureComment.getCommentsString(count),
                                        get_date_for_slides(count),
                                        " ".join(Tag.getTagNames(count)))
                pi.comment = tmpText
                pictureIndices.append(pi)

        template_values = {
            'pics': pictureIndices,
            'displaywidth': 640,
            'pictureheight': 900,
            'containerheight': 900+160,
        }
        template_text = render_template_text('filmstrip.html', template_values)
        return template_text

    def get(self, index=None):
        if index is not None:
            index = int(index)
        templateText = self.get_filmstrip_html(current_index=index)
        self.write_output(templateText)

class ImagesByTagHandler(RequestHandlerParent):
    def get(self, tag_name=None):
        if tag_name is None:
            tag_name = self.request.get('tag')
        isDesc = 'asc' != str(self.request.get('order'))
        memcache_name = "memcache tag %s %s" % (tag_name, isDesc)
        #memcache_name = get_memcache_name(ImagesByTagHandler,
        #                                 tagName=tag_name,
        #                                 isDesc=isDesc)
        outText = memcache.get(memcache_name)
        if outText is None:
            uniqueTagName = UniqueTagName.all().filter('name', tag_name).get()
            tags = Tag.all().filter('name_ref', uniqueTagName).order('date')

            pi_counts = [tag.count for tag in tags]
            if len(pi_counts) > 20:
                pis = []
                for pi_count in pi_counts:
                    pi = PictureIndex.all().filter('count', pi_count).get()
                    pis.append(pi)
            else:
                pis = PictureIndex.all().filter('count in', pi_counts)

            # TODO add ordering here?
            pi_dicts = [pi.template_repr() for pi in pis]
            pi_dicts.sort(key=lambda x: x['dateOrderIndex'])

            logging.info('tag is %s', tag_name)
            logging.info('pis are %s', pi_dicts)
            template_values = {
                'current_index': 10, # why not?
                'newest_index': highest_picture_index(),
                'tag_name': tag_name,
                'carousel_slides': pi_dicts,
            }

            outText = render_template_text('images_by_tag.html', template_values)
            memcacheStatus = memcache.set(memcache_name, outText)
            if not memcacheStatus:
                logging.debug("memcaching failed in ImagesByTagHandler")
            else:
                logging.debug("memcaching was set in ImagesByTagHandler")
        else:
            logging.info("memcaching worked in ImagesByTagHandler for %s" %
                         memcache_name)

        self.write_output(outText)

